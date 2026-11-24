# fx-reporting-pipeline

A small ELT pipeline for financial reporting. It pulls FX rates from a free public API
(Frankfurter), generates synthetic position data, loads both into DuckDB, uses dbt to convert
every position into EUR, and runs automated data-quality tests on the result. An Airflow DAG
runs the steps in order, and GitHub Actions runs the pipeline and tests on every push.

Positions are synthetic (there is no public source for real holdings), and the sample data
covers only a couple of dates. This is a learning project, not a production system.

## How it works

```
FX API + position generator -> raw JSON -> DuckDB -> dbt (staging -> intermediate -> marts) -> tests
```

1. **Extract:** two Python scripts write raw JSON, one folder per date. Re-running a date
   overwrites the file instead of adding a duplicate.
2. **Load:** the raw JSON is loaded into DuckDB.
3. **Transform (dbt):** staging cleans the data, the intermediate model joins each position to
   the FX rate for its date and computes `eur_value = amount / rate`, and the marts hold the
   per-position valuation and a daily EUR total.
4. **Test:** 11 dbt tests (not null, unique, accepted values, positive value) plus 8 pytest
   unit tests for the extractors.
5. **Orchestrate:** an Airflow DAG (Docker Compose) runs extract, load, `dbt run`, `dbt test`
   with retries. CI runs the same steps plus pytest.

## Run it

Needs Python 3.12.

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

python extractors/fx_rates.py
python extractors/positions.py
python warehouse/load_raw.py

cd dbt_project
dbt run --profiles-dir .
dbt test --profiles-dir .
cd ..

pytest tests/
```

Airflow (tested on Windows with Docker Desktop): `cd airflow_docker`, then
`docker compose up airflow-init`, then `docker compose up -d`. The UI is at
http://localhost:8081 (user `airflow`, password `airflow`, local use only).

## What I found

**A silent data bug.** The raw files live in folders named `date=YYYY-MM-DD/`, and the FX JSON
also had its own `date` field. When loading, DuckDB treated the folder name as a column and
quietly used it instead of the field in the file. No error. The real source date of each rate
(for weekends, the earlier business day the API falls back to) was being overwritten. I only
noticed because the loaded table disagreed with the raw file when I compared them, and I
confirmed the cause by loading the same file with partition detection on and off. The fix was to
rename the field to `rate_date`. Details: ADR-008 in `docs/system-design.md`.

**Two defects can hide each other.** To check that the tests really catch bad data, I injected
defects into the raw layer (`tests/defect_injection_eval.py`). A null rate, a duplicate key and
an orphan position were each caught. A negative amount was not caught by its own test: it landed
on the same row as the null rate, so `eur_value` was NULL, and `NULL <= 0` is not true in SQL,
so the "value must be positive" check skipped the row. Another test still flagged that row, but
for the other defect. A test suite can look healthy and still have blind spots when problems
overlap.

## Known limitations

- **The join is an equality join on the requested date.** Weekends work because the API fills
  in the previous business day's rate (and `rate_date` records which day), not because the SQL
  does a "latest rate on or before" lookup. The sample positions are all on a weekday, so the
  weekend case isn't tested end to end. See ADR-007.
- **Tests run after the marts are built.** A failing test fails the run, but the marts have
  already been rebuilt, so bad data is detected rather than prevented.
- **The "daily" DAG reprocesses fixed sample dates.** The extractors don't take a date yet.
- **No stale-data check:** nothing detects that rates stopped updating.
- **The NL→SQL assistant (`llm_assistant/`) was never run against a live model.** Its SQL
  validator and schema code are tested; the model call needs a paid API key.
- Not built: Snowflake port, dashboard.

## More detail

- [`docs/system-design.md`](docs/system-design.md): the design decisions, with context and
  consequences for each.
- [`docs/learning-log.md`](docs/learning-log.md): what I learned and the bugs I hit, in order.
- [`docs/runbook.md`](docs/runbook.md): what to do when something breaks.
