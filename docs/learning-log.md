# Learning log

Running record of concepts covered, decisions made, and bugs actually hit while building
this project. Updated after every task. This is the evidence that the repo reflects real
understanding, not just working code.

## Milestone 0 — Environment & repo skeleton

**Concepts covered:**
- **Python version pinning.** Machine had Python 3.9 (EOL Oct 2025) and 3.14 (too new —
  tools like dbt/Airflow lag behind the newest Python release). Installed 3.12 deliberately
  as the "boring middle" choice, rather than trusting whichever `python` happened to resolve
  on PATH.
- **`py -3.12 -m venv venv` vs bare `python -m venv venv`.** A bare `python` command uses
  whatever the OS PATH resolves first — on this machine that was the old 3.9, not the 3.12
  just installed. Being explicit about the version avoids silently building on the wrong one.
- **git tracks files, not folders.** Empty directories (`extractors/`, `dbt_project/`, etc.)
  don't show up in `git status` or get committed until a file exists inside them.
- **`.gitignore` reasoning.** Secrets (`.env`) and anything regenerable (venv, raw landed
  data, dbt build artifacts) don't belong in version control — only source/config does.

## Milestone 1 — FX extractor

### Task 1 — `fetch_fx_rates()`

**Concepts covered:**
- **Idempotency.** An operation is idempotent if running it N times produces the same end
  state as running it once. Matters here because Airflow will retry failed tasks
  automatically (Milestone 7) — a non-idempotent extractor could silently double-count data
  on retry.
- **Pure functions.** Keeping "fetch data" separate from "save data" makes the fetch logic
  testable in isolation (mocked HTTP calls, no real network needed) later in Milestone 9.
- **`response.raise_for_status()`.** `requests` does not raise on 4xx/5xx by default — without
  this call, a failed request fails silently instead of loudly, and `.json()` on an error
  page can produce garbage that looks like valid data.
- **Frankfurter API behavior (confirmed live, not assumed):** no API key required;
  `?base=USD&symbols=EUR,GBP` params; requesting a weekend date returns the most recent
  prior business day's rate instead of erroring — the API **forward-fills** silently. This
  directly affects how "freshness" and the future FX join (Milestone 4/5) must be designed —
  "no data today" is *expected* on weekends, not a failure signal.

**Bugs actually hit and fixed (first attempt):**
- Dict literal used `=` instead of `:` (syntax error — code wouldn't parse).
- Typo `equests.get(...)` instead of `requests.get(...)` (would be a `NameError`).
- Missing `return response.json()` — function always returned `None` even when everything
  else worked. Most severe bug: no crash, no error, just silently useless output.
- `symbols` passed as a raw Python list into the request params instead of being joined into
  a comma-separated string (`",".join(symbols)`), which is the format the API expects.

### Task 2 — `save_fx_rates()`

**Concepts covered:**
- **`os.makedirs(path, exist_ok=True)` vs `os.mkdir(path)`.** `os.mkdir` creates only one
  directory level and has no `exist_ok` option at all — it errors if the target already
  exists. `os.makedirs` creates every missing parent directory in one call, and `exist_ok=True`
  means "don't error if it's already there" — required for idempotent re-runs, since the
  second run for the same date will find the folder already exists.
- **Folder path vs full file path.** The directory to create (`data/raw/fx_rates/date=.../`)
  is not the same string as the file to open (`.../rates.json`) — creating a directory at the
  full file path would make a folder literally named `rates.json`.
- **`os.path.join` vs `os` module functions.** `os` handles OS-level operations (creating
  dirs, env vars); `os.path` handles path-string manipulation. `os.join` does not exist.
- **Hive-style partitioning.** The `date=2024-01-15` folder-naming convention is a real
  pattern recognized by query engines (Spark, Athena, DuckDB) that can glob `date=*` and
  know what partition column a folder represents without opening any files.
- **Overwrite (`"w"` mode) vs append (`"a"` mode).** Opening a file in `"w"` mode replaces
  its contents entirely — this is what makes re-running `save_fx_rates` for the same date
  safe (overwrite) instead of duplicative (append).

**Bugs actually hit and fixed:**
- `os.mkdir(path, exist_ok=True)` — `exist_ok` isn't a valid argument to `os.mkdir` at all
  (that's `os.makedirs` only); also `path` included the filename, not just the folder.
- `os.join(...)` instead of `os.path.join(...)` — `AttributeError`, wrong module.

**Verified (not just assumed) idempotency:** ran the script twice in a row; `data/raw/fx_rates/`
contains exactly one file per date afterward, both runs.

**Design decision:** landing format is JSON, not parquet, for now — parquet needs
`pyarrow`/`pandas` and is meant for large tabular data; overkill for a handful of exchange
rates while still learning the core partitioning/idempotency pattern. Swapping formats later
is a contained change, isolated to `save_fx_rates`.

### Task 3 (Milestone 1) — synthetic positions extractor

**Concepts covered:**
- `random.seed(date)` for deterministic-but-varied synthetic data (same date = same output,
  different dates = different output). Distinguished from idempotency: seeding controls
  *what data gets generated*; the file-write pattern separately controls *how safely it gets
  saved*. Both are needed together.
- Honest scoping: `random.uniform(1000, 500000)` for position amounts is an arbitrary
  placeholder for believable mock data, not a claim about how real position sizes are
  actually distributed (which would be skewed/log-normal in reality, not uniform).

## Milestone 2 — load raw JSON into DuckDB

**Concepts covered:**
- **DuckDB as an embedded OLAP engine.** No server process — a single file on disk, built
  for scanning/aggregating rather than many small transactional reads/writes. Can query
  JSON/CSV/Parquet files directly via `read_json_auto(glob_pattern)` without a manual
  parsing loop.
- **`con.sql("...")` pattern.** Every operation is just a SQL string handed to the
  connection object. A bare `SELECT` only returns a result in memory; `CREATE OR REPLACE
  TABLE x AS SELECT ...` is what actually persists it into the database file.
- **Windows console encoding.** `UnicodeEncodeError` when printing DuckDB's `.show()` output
  — Windows terminals often default to a legacy codepage (`cp1252`) instead of UTF-8, and
  DuckDB's table-drawing characters aren't in that codepage. Fixed once, in the script
  itself (`sys.stdout.reconfigure(encoding="utf-8")`), rather than as a one-off terminal
  workaround, since the same script needs to behave identically inside Airflow later.
- **DuckDB Hive-partition auto-detection — real bug found and fixed, not a scaffolded one.**
  See ADR-008 in system-design.md for the full writeup. Short version: naming a partition
  folder `date=...` (ADR-005) while the file's own JSON content also had a `date` field
  caused DuckDB to silently substitute the folder's value for the real one, discarding the
  actual forward-filled rate date with no warning. Found by comparing the loaded table's
  output against the raw file's literal content (`cat` the file directly) rather than
  trusting that "the script ran without error" meant the data was correct. Confirmed the
  root cause with a direct A/B test (`hive_partitioning=true` vs `false`) before fixing.
  Fixed by renaming the colliding field (`date` -> `rate_date`) at the source, in
  `fetch_fx_rates()`, and regenerating the raw data rather than patching it by hand.

**Debugging process actually used (reproduce -> isolate -> hypothesize -> confirm -> fix ->
verify):** noticed the loaded date looked wrong -> compared it against the known-correct
value from an earlier `fetch_fx_rates` call -> hypothesized a Hive-partitioning collision ->
confirmed with an A/B DuckDB query before touching any code -> fixed at the source ->
reloaded and verified both `date` and `rate_date` now appear correctly and diverge exactly
on the weekend record.

## Milestone 3 — dbt

**Setup (mechanical, done by Claude, explained not hand-typed):** `dbt-core` + `dbt-duckdb`
installed; `dbt_project.yml` (project config, default materialization), `profiles.yml`
(connection — the only file that changes when we port to Snowflake later, per ADR-002),
`_sources.yml` (declares `raw.fx_rates`/`raw.positions` so models can use `source()` instead
of hardcoding table names, which is what lets dbt build its dependency graph).

### Task 1 — `stg_positions.sql`

**Concepts covered:**
- A dbt model is just a `.sql` file with a `SELECT` — the filename becomes the view/table
  name, dbt wraps the DDL automatically.
- **Staging = strict 1:1 cleanup, no business logic.** Explicit column lists instead of
  `SELECT *`, so staging acts as a contract — a new column appearing upstream doesn't
  silently flow downstream unnoticed.
- **dbt's default custom-schema behavior is not what it looks like.** Setting `+schema:
  staging` in `dbt_project.yml` does **not** put models in a schema literally called
  `staging` by default — dbt prefixes it with the target schema (`main_staging`). Fixed with
  the standard `generate_schema_name.sql` macro override (a well-known, documented dbt
  pattern, not a custom hack) so custom schema names are used literally.
- Verified with real data, not just "it ran": queried `information_schema.tables` directly
  to confirm only `staging.stg_positions` exists after the fix, and dropped the orphaned
  `main.stg_positions` left over from before the schema config was corrected.

### Task 2 — `stg_fx_rates.sql`

**Real design correction found while planning this task (ADR-010):** the extractor
defaulted to `base=USD`, but the pipeline converts everything *to* EUR — so `base=EUR` is
what actually gives a direct per-currency rate for every position currency in one call.
Fixed at the source and regenerated raw data.

**Concepts covered:**
- **Wide vs long (tall) data shape.** `raw.fx_rates` has one row per date with all
  currencies side-by-side in a struct (wide). Joining against positions (one currency each)
  needs one row per date *per currency* (long). `UNION ALL` across one `SELECT` per currency
  reshapes wide into long.
- **`UNION ALL` vs `UNION`** — always prefer `ALL` unless deduplication is specifically
  wanted; plain `UNION` silently drops rows it considers duplicates, which can mask a real
  bug instead of surfacing it.
- **DuckDB lowercases JSON struct field names** — `rates.usd`, not `rates.USD`, even though
  the source JSON had uppercase keys.

**Verified:** 8 rows (2 dates x 4 currencies), correct rates, and `rate_date` still shows the
forward-filled date distinctly from `date` on the weekend row — the point-in-time signal
survived the full path from API to staging.

## Milestone 4/5 — intermediate join, marts, tests, defect-injection eval

**Concepts covered:**
- **`ref()`** used for real for the first time — `int_position_valuations` references
  `stg_positions`/`stg_fx_rates` (other models), not raw sources, extending the DAG one
  layer further. dbt built all 5 models in the correct order automatically.
- **`LEFT JOIN` deliberately, not `INNER JOIN`.** An unmatched position becomes a visible
  `NULL` row instead of silently vanishing — matches the "never silently drop data" theme
  from the very first architecture review.
- **Materialization choice:** marts use `+materialized: table` (physically stored — reports
  get read often, built once), staging/intermediate stay `view` (cheap, always live).
- **dbt generic tests** (`not_null`, `unique`, `accepted_values`) vs **singular tests**
  (`tests/assert_positive_eur_value.sql` — a plain `SELECT` of violating rows; the test
  passes only if it returns zero rows).
- **Real defect-injection eval, not simulated** (`tests/defect_injection_eval.py`) — 4
  defects actually injected into raw tables, `dbt test` actually run and actually failed (4
  errors), then reset by re-running `load_raw.py` (raw is always rebuilt from untouched
  source JSON, so "undo" is just "reload"). Full results table in README.md.
- **Real, unplanned finding:** two defects landing on the same row can mask each other
  (`NULL <= 0` is not true in SQL) — a genuine test-coverage blind spot, not something I set
  out to demonstrate. Documented honestly rather than hidden.
- **Known, explicitly flagged gap:** "stale date" isn't caught by any current test — that
  requires freshness checking, which doesn't exist until the Airflow milestone.

## Up next — Milestone 7 (Airflow), then docs polish
