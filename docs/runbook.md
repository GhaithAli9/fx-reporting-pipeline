# Runbook

Operational reference for running and troubleshooting the pipeline. See `system-design.md`
for *why* things are built this way; this doc is for *what to do* when something breaks.

## Manual daily run (until Airflow is actually running — see ADR-012)

```bash
./venv/Scripts/python.exe extractors/fx_rates.py
./venv/Scripts/python.exe extractors/positions.py
./venv/Scripts/python.exe warehouse/load_raw.py
cd dbt_project
../venv/Scripts/dbt.exe run --profiles-dir .
../venv/Scripts/dbt.exe test --profiles-dir .
```

If `dbt test` fails, **do not** consider the marts published — that's the entire point of
gating on tests. Fix the root cause, don't patch the mart data by hand.

## If a dbt test fails

1. The failing test's name tells you the model and column (e.g.
   `not_null_fct_position_valuation_eur_value`).
2. Query the model directly to see the actual offending rows, e.g.:
   `SELECT * FROM marts.fct_position_valuation WHERE eur_value IS NULL`
3. Trace back to *why* — usually a missing/null upstream value (raw data issue) or a join
   grain problem (Duplicate/missing FX rate for a currency+date). Fix the extractor or the
   model, never the mart output directly.
4. Re-run `warehouse/load_raw.py` (rebuilds raw from source JSON) then `dbt run && dbt test`.

## If the FX API extractor fails

- Check the exception — `requests.exceptions.HTTPError` means the API responded with an
  error status; a connection error means the API is unreachable.
- The Frankfurter API has no published SLA. If it's down, the correct behavior is to **skip
  that day's run rather than publish stale or partial data** — this isn't automated yet
  (planned as a freshness/SLA check once Airflow is running, ADR-012).

## If the DuckDB file seems locked / won't open

DuckDB is embedded — only one process can hold the file open for writing at a time. Close
any other Python REPL, dbt process, or script that still has a connection open, then retry.

## Resetting to a clean state

- **Raw data only:** re-run the extractors, then `python warehouse/load_raw.py` — raw tables
  are always rebuilt from the untouched source JSON files, never hand-edited.
- **Full reset:** delete `warehouse/fx_reporting.duckdb`, then re-run `load_raw.py` followed
  by `dbt run`.

## Where things are documented

- `docs/system-design.md` — every real architecture decision, why, and its consequences
  (ADR format).
- `docs/learning-log.md` — concepts covered and real bugs found, in the order they happened.
