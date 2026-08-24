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

## Up next — Milestone 1 continued / Milestone 2

- Second source (positions/transactions) — not started.
- Load raw JSON into DuckDB raw schema (Milestone 2).
