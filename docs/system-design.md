# System design & architecture decisions

Living document. Updated at every milestone, not written retroactively at the end.
Decisions are logged ADR-style (Context / Decision / Consequences) so the *why* behind
the system survives independently of git history.

## Architecture overview

```
Frankfurter API --> extractor (fetch + save) --> raw JSON, date-partitioned   [BUILT]
                                                        |
                                                        v
                                            DuckDB raw schema                  [PLANNED - M2]
                                                        |
                                                        v
                                   dbt: staging -> intermediate -> marts       [PLANNED - M3-M6]
                                                        |
                                                        v
                                        dbt tests gate mart publication        [PLANNED - M5+]
                                                        |
                                    -----------------------------------
                                    |                                 |
                              Airflow orchestrates            NL->SQL LLM assistant
                              the whole chain, with           reads marts read-only,
                              retries + freshness gating       schema-grounded, validated
                                    [PLANNED - M7]                    [PLANNED - M10]
```

## Decision log

### ADR-001: Python 3.12, pinned explicitly
**Context:** machine had Python 3.9 (EOL Oct 2025, no security patches) and 3.14 (released
recently — dbt/Airflow historically lag a release or two behind newest Python; risk of
missing wheels for compiled dependencies).
**Decision:** install Python 3.12 separately, and always invoke the venv creation with
`py -3.12 -m venv venv` rather than a bare `python` command.
**Consequences:** reproducible environment; avoids a bare `python` command silently
resolving to whichever version happens to be first on PATH (which was 3.9 here — the one
version we specifically wanted to avoid).

### ADR-002: DuckDB now, Snowflake later, via dbt's connection abstraction
**Context:** need a free, fast, local warehouse to iterate against, but the target job
(and the CV story) wants real Snowflake exposure too.
**Decision:** build all dbt models against DuckDB first; port to a Snowflake trial once the
core models/tests are solid (Milestone 12).
**Consequences:** dbt's `profiles.yml` makes the connection swap mechanically easy, but SQL
dialect differences (date functions, incremental-model strategies, macro portability) are
not automatically handled — expect to name specific things that needed adjustment when
porting, not claim it "just worked."

### ADR-003: FX data source = Frankfurter API
**Context:** needed a free FX rate source with minimal friction (no key management for a
learning project) and real, defensible data.
**Decision:** use `https://api.frankfurter.dev/v1/{date}?base=...&symbols=...` — no API key,
ECB reference rates.
**Consequences:** confirmed live (not assumed) that requesting a non-business-day date
forward-fills to the most recent prior rate rather than erroring. This means any freshness
check or point-in-time join built later must treat "no new data on a weekend" as expected
behavior, not a failure signal.

### ADR-004: Raw landing format = JSON, not parquet
**Context:** original plan specified parquet for raw landing; parquet needs `pyarrow`/
`pandas` and is a columnar format meant for large tabular datasets.
**Decision:** land as plain JSON for now, one file per partition.
**Consequences:** zero extra dependencies while the core extractor/idempotency pattern is
still being learned. Isolated, contained change if/when parquet is introduced later — only
`save_fx_rates` needs to change, nothing downstream depends on the file format directly.

### ADR-005: Hive-style date partitioning for raw data
**Context:** raw files need a layout that supports idempotent overwrite-by-date and is
recognizable to query engines later (DuckDB, and eventually Snowflake).
**Decision:** `data/raw/fx_rates/date=YYYY-MM-DD/rates.json`.
**Consequences:** matches a convention (`date=value` folder naming) that DuckDB, Spark, and
Athena all auto-recognize for partition pruning — not a project-specific invention.

### ADR-006 (built — see ADR-014): least-privilege DB role for the LLM assistant
**Context:** the NL->SQL assistant (Milestone 10) will execute LLM-generated SQL. Relying
solely on parsing/regex-filtering the generated SQL for safety is a weak, single-layer
defense — a parser bug or an unanticipated SQL construct could slip through.
**Decision:** the LLM assistant's DB connection will use a separate, scoped credential with
read-only grants on the marts schema only — never the credential the pipeline itself uses to
write data. The SQL validator is the first layer of defense, not the only one.
**Consequences:** even if the validator has a bug, the database itself refuses writes and
refuses access to raw/staging data. Not yet implemented — flagged here so it isn't forgotten
or descoped under time pressure later.

### ADR-007: FX join — equality on the requested date, as-of behavior delegated to the source API (built; see ADR-011)
**Context:** naively joining positions to FX rates "on date" breaks on weekends/holidays,
because no rate is published for those days. The join needs a rule for which rate applies to
a position dated on a non-business day. This is the highest-risk part of the project: a wrong
grain here produces plausible-looking but wrong valuations.
**Original proposal:** a true as-of join in SQL — "most recent rate on or before the
position's business date, per currency".
**Decision (what the code actually does):** `int_position_valuations` does an equality
`LEFT JOIN` on `currency` and `business_date = date`, where `date` is the *requested* date the
extractor asked the API for. The as-of behavior is delegated to the source: the Frankfurter API
forward-fills a non-business day to the most recent prior business day, and the real source date
is preserved in `rate_date` (see ADR-003 and ADR-008). A weekend position therefore gets Friday's
rate, and `rate_date <> business_date` makes that staleness visible.
**Consequences / limitations:**
- Correctness depends on the extractor having requested a rate for every position
  `business_date`. A position on a date with no fetched rate row does **not** fall back to an
  earlier rate: its `eur_value` is NULL and the `not_null` test on
  `fct_position_valuation.eur_value` fails. The pipeline fails loudly instead of guessing.
- The as-of logic lives in an external API's behavior, not in the SQL. If that behavior
  changed, the symptom would be missing rates (caught by the test above), not silently wrong
  ones.
- The weekend path through the join is not exercised by the current sample data: sample
  positions exist only for 2024-01-15 (a weekday), so no position joins to the 2024-01-13
  (forward-filled) rate row. That path is not covered end to end by any test yet.
- Not implemented: a SQL-level as-of join (e.g. DuckDB `ASOF JOIN` on `rate_date <=
  business_date`). That would remove the dependence on the API and on fetching every date, and
  is the planned improvement, to be paired with a test that has a position on a weekend date.

### ADR-007b: positions data = deterministic synthetic generator
**Context:** no free public API exists for company position/holdings data (it's internal to
a real institution).
**Decision:** generate synthetic positions with Python's `random`, seeded from the business
date itself (`random.seed(date)`), not a single global fixed seed.
**Consequences:** same date always generates the same positions (idempotent, reproducible —
matches ADR for the FX extractor), while different dates produce different-looking data
(more realistic than a static fixture repeated every day). Clearly labeled as synthetic in
the README so it's never presented as real financial data.

### ADR-008: `rate_date` renamed to avoid Hive-partition column shadowing
**Context:** while loading raw JSON into DuckDB (Milestone 2), discovered that
`read_json_auto` auto-detects the `date=value` Hive-style partition folders (ADR-005) and
injects a `date` column from the folder name — which silently overrode the `date` field
already present in the fx_rates JSON content, with no error or warning. Confirmed via a
direct A/B test (`hive_partitioning=true` vs `false` on the same file) that the folder value
was winning and the actual API-returned date (the forward-filled rate date on weekends) was
being lost. Caught by comparing the loaded table's output against the raw file's literal
content, not by assuming the load was correct because it ran without error.
**Decision:** renamed the field in `fetch_fx_rates()`'s return value from `date` to
`rate_date` before it's ever saved, removing the name collision entirely.
**Consequences:** `date` (from the partition) now consistently means "the business date this
data was requested/reported for" across every raw table. `rate_date` (from content) means
"the date this specific rate is actually dated from" — and the two columns now visibly
diverge exactly on weekends/holidays, which is precisely the staleness signal the
point-in-time FX join (ADR-007) needs. Existing raw fx_rates data was deleted and
regenerated from the extractor rather than patched in place — raw data is always
regenerable, never hand-edited.
**General lesson for future partition-key choices:** never name a partition folder the same
as a field that already exists in the file's own content — verify loaded output against raw
file content directly rather than trusting "it ran without error."

### ADR-009 (planned, not yet built): `profiles.yml` credentials before Snowflake
**Context:** `dbt_project/profiles.yml` is currently committed to git — safe today because
the DuckDB connection has no username/password, just a local file path. This stops being
safe the moment Snowflake credentials (ADR-002/ADR-012) go into this file.
**Decision:** before the Snowflake port, switch `profiles.yml` to use dbt's `env_var(...)`
macro for the credential fields, sourced from `.env` (already git-ignored), instead of
literal values in the file.
**Consequences:** flagged now, before it's forgotten under momentum — committing real
warehouse credentials would be a genuine security incident, not just a style issue.

### ADR-010: fetch FX rates with `base=EUR`, not `base=USD`
**Context:** the pipeline's whole purpose is converting positions (held in USD/GBP/JPY/CHF)
into EUR. The extractor originally defaulted to `base=USD`, which only gives a direct rate
for USD positions — GBP/JPY/CHF would each need separate cross-rate logic.
**Decision:** default `fetch_fx_rates` to `base=EUR`, and always request the full fixed set
of position currencies (`POSITION_CURRENCIES = ["USD","GBP","JPY","CHF"]`) as `symbols`.
**Consequences:** every position currency now gets a direct "units per 1 EUR" rate in a
single API call (e.g. `rates.USD = 1.0945` means 1 EUR = 1.0945 USD), so converting any
position is just `eur_value = amount / rates.<CCY>` — no per-currency special-casing needed.
Also means every fx_rates row now has a consistent, predictable set of struct fields (always
exactly CHF/GBP/JPY/USD, never a subset) — which is what makes a simple, static unpivot into
staging possible without dynamic SQL generation. Raw data was regenerated, not patched.

### ADR-011: intermediate join + marts + tests built
**Decision:** `int_position_valuations` joins `stg_positions` to `stg_fx_rates` on
`currency` and `business_date = date` (LEFT JOIN, deliberately — an unmatched position
becomes a visible NULL, never a silently dropped row). `fct_position_valuation` (table) and
`rpt_daily_eur_exposure` (table, aggregated) are the marts. 11 dbt tests across staging/marts
(not_null, unique, accepted_values, one singular test for positive `eur_value`).
**Consequences:** the "stale date" defect (#4 in the eval table) is **not** caught by any
current test — it requires a freshness check (dbt source freshness + Airflow SLA), which
doesn't exist until Milestone 7. Flagged explicitly rather than silently left uncovered.
**Real finding:** two injected defects on the same row (null rate + negative amount) masked
each other, since `NULL <= 0` is not true in SQL — the singular test missed it, though a
different `not_null` test still caught the row for an unrelated reason. See README for the
full eval table.

### ADR-012: Airflow running via Docker Compose (LocalExecutor)
**Context:** Docker Desktop was installed (WSL2 backend, already enabled on this machine).
Used Apache Airflow's own published `docker-compose.yaml` (2.10.4) rather than hand-writing
one, then simplified it: swapped `CeleryExecutor` for `LocalExecutor` and removed
redis/worker/triggerer/flower entirely, since a single-DAG local demo doesn't need a
distributed task queue. Added a bind mount of the whole project to `/opt/project` in every
Airflow container so the DAG's bash commands can reach `extractors/`, `dbt_project/`, and
`warehouse/` directly. Used `_PIP_ADDITIONAL_REQUIREMENTS` (documented by Airflow as
appropriate for "quick checks," which matches this use case) to install `duckdb`,
`dbt-core`, `dbt-duckdb`, `requests` into the containers rather than building a custom image.
**Decision:** `LocalExecutor` + postgres + webserver + scheduler only, project mounted at
`/opt/project`, webserver on host port 8081 (8080 was already bound by something else on
this machine).
**Real bugs hit and fixed while getting this running:**
1. Port 8080 conflict — moved the host mapping to 8081 rather than hunting down what else
   had it.
2. `dbt_run` failed with `KeyError: 'fx_reporting://macros/generate_schema_name.sql'` — a
   stale `dbt_project/target/` partial-parse cache, built by many prior runs directly on
   Windows, became inconsistent when read fresh inside the container. Fixed by deleting
   `target/` and `logs/` to force a clean parse — confirmed the fix in isolation
   (`docker compose exec ... dbt run`) before trusting Airflow's automatic retry to prove it.
3. Unpausing the DAG auto-scheduled the most recent daily interval *in addition to* the
   manual trigger (`catchup=False` only skips the historical backlog, not the latest run) —
   two DAG runs executing `dbt_run` concurrently. Not fully resolved (documented, not hidden):
   this is a real concurrency question for a single-writer embedded database like DuckDB, and
   the honest answer for now is "don't manually trigger while a scheduled run might also be
   due" — a proper fix (unique run-scoped DB paths, or a warehouse that handles concurrent
   writers) is a real hardening item, not solved here.
**Consequences:** full DAG run proven end-to-end for real — `extract_fx_rates`,
`extract_positions`, `load_raw`, `dbt_run`, `dbt_test` all reached `success` in Airflow's own
task history, not just claimed. Screenshots/logs available via `docker compose logs` and the
webserver UI at `localhost:8081`.

### ADR-013: CI via GitHub Actions, verified locally with `act` before pushing
**Context:** wanted CI running dbt tests on every push (mirrors the "tests gate merge"
principle already core to this project), but writing a workflow YAML and hoping it works
after pushing to GitHub violates the whole verify-don't-assume approach used everywhere else
here.
**Decision:** `.github/workflows/ci.yml` runs the same sequence already verified manually
(extract -> load -> `dbt run` -> `dbt test`) on a fresh checkout, Python 3.12. Downloaded
`act` (a tool that simulates GitHub's own Actions runners using Docker, which was already
set up for Airflow) and ran the workflow locally before ever touching GitHub.
**Consequences:** confirmed for real — 5 dbt models built, 11 tests passed, inside an actual
simulated Actions runner container, not just "ran fine on my machine." The workflow file
pushed to GitHub is the exact one already proven to work, not a first attempt.

### ADR-014: NL->SQL assistant — schema grounding + parser-based validation built
**Context:** implementing ADR-006's design now. DuckDB has no grantable roles (it's an
embedded, single-file database, not a client-server one), so "least-privilege read-only
role" needed a DuckDB-native equivalent.
**Decision:**
- `llm_assistant/schema.py` introspects `information_schema.columns` for the `marts` schema
  live from the database on every call, rather than a hand-typed schema string that could
  drift out of sync.
- `llm_assistant/validator.py` uses `sqlglot` (a real SQL parser) instead of regex/keyword
  matching: rejects anything that isn't exactly one `SELECT` statement, walks the full parse
  tree for write/DDL node types as defense in depth, restricts table access to the `marts`
  schema by inspecting each `Table` node's schema qualifier, and enforces/caps a row `LIMIT`.
- The DuckDB connection the assistant executes against is opened with `read_only=True` --
  DuckDB's actual mechanism for "this connection cannot write," which is the real equivalent
  of the least-privilege role originally planned for Postgres/Snowflake.
**Consequences:** two independent layers, verified separately before wiring together — the
validator was tested against 5 cases (including a DELETE and a multi-statement SQL
injection attempt) with zero LLM calls involved, and passed all 5 before the assistant's own
LLM-calling code was even tested end to end.

**Status: code-complete, not executed against a live API.** `llm_assistant/assistant.py`
(the actual Claude API calls, orchestration, and one-shot repair loop) is written and ready
to run, but exercising it costs real (if small) money, and a deliberate decision was made
not to spend that while finalizing the project to apply. This is the same honest-scoping
pattern as ADR-012 (Airflow was written before it was actually run) — the schema-grounding
and validation layers, the parts that don't need paid API calls, *are* fully verified above;
only the final "call the real model and look at a real answer" step is deferred. Running it
just needs an `ANTHROPIC_API_KEY` in `.env` — no code changes.
