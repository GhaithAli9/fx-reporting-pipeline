# fx-reporting-pipeline

An end-to-end ELT pipeline that ingests FX and position data, transforms it into
audit-ready reporting marts with dbt, orchestrates the flow with Airflow, enforces
data-quality tests, and exposes a schema-grounded LLM assistant for natural-language
querying.

Status: under construction (Milestone 0 — environment setup).

## Project layout

- `extractors/` — Python scripts that pull raw data from source APIs and land it,
  partitioned by date, immutably.
- `dbt_project/` — dbt models: staging (clean/typed) -> intermediate (business logic,
  e.g. FX conversion) -> marts (reporting-ready tables), plus data-quality tests.
- `dags/` — Airflow DAG(s) orchestrating extract -> load -> dbt run -> dbt test.
- `tests/` — Python unit tests (extractors, FX math, SQL validator).
- `docs/` — system-design.md and runbook.md.
