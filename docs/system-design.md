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

### ADR-006 (planned, not yet built): least-privilege DB role for the LLM assistant
**Context:** the NL->SQL assistant (Milestone 10) will execute LLM-generated SQL. Relying
solely on parsing/regex-filtering the generated SQL for safety is a weak, single-layer
defense — a parser bug or an unanticipated SQL construct could slip through.
**Decision:** the LLM assistant's DB connection will use a separate, scoped credential with
read-only grants on the marts schema only — never the credential the pipeline itself uses to
write data. The SQL validator is the first layer of defense, not the only one.
**Consequences:** even if the validator has a bug, the database itself refuses writes and
refuses access to raw/staging data. Not yet implemented — flagged here so it isn't forgotten
or descoped under time pressure later.

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

### ADR-007: point-in-time FX join (planned, not yet built)
**Context:** naively joining positions to FX rates "on date" breaks on weekends/holidays
(no rate exists) and risks using the wrong rate if not handled explicitly.
**Decision:** the intermediate join (Milestone 4/5) will use "most recent rate on or before
the position's business date, per currency" — designed and written down *before* being
implemented in SQL.
**Consequences:** this is the highest-risk part of the whole project; getting the grain
wrong here would silently produce plausible-but-wrong valuations downstream.
