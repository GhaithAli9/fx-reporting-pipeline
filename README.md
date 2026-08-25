# fx-reporting-pipeline

An end-to-end ELT pipeline that ingests FX and position data, transforms it into
audit-ready reporting marts with dbt, orchestrates the flow with Airflow, enforces
data-quality tests, and exposes a schema-grounded LLM assistant for natural-language
querying.

Status: under construction (Milestone 0 — environment setup).

## Data quality: defect-injection evaluation

To prove the dbt tests actually catch bad data (not just pass trivially), `tests/defect_injection_eval.py`
injects 5 realistic defects into the raw layer, then runs the full model + test suite against
the corrupted data.

| # | Defect | Caught by | Result |
|---|--------|-----------|--------|
| 1 | Null FX rate | `not_null` on `stg_fx_rates.rate` | Caught (1 row) |
| 2 | Duplicate position key | `unique` on `stg_positions.position_id` / `fct_position_valuation.position_id` | Caught (both layers) |
| 3 | Out-of-range value (negative amount) | `assert_positive_eur_value` (singular test) | **Not caught** in this run — see note below |
| 4 | Stale date (no fresh data for N days) | *not covered yet* | Planned: dbt source freshness + Airflow SLA (Milestone 7) |
| 5 | Orphan position (no matching FX rate for its date) | `not_null` on `fct_position_valuation.eur_value` | Caught (4 rows — includes the orphan plus 3 positions hit by defect 1) |

**Finding worth calling out:** defect 3 landed on a USD position on the same date as defect 1
(the null rate). `eur_value = -50000 / NULL = NULL`, and `NULL <= 0` evaluates to unknown in
SQL — not true — so the singular test's `WHERE eur_value <= 0` filter didn't match that row.
Two defects on the same row masked each other. The `not_null` test on `eur_value` still caught
the row (for the null-rate reason), but it's a real reminder that overlapping defects can create
blind spots even in a passing-looking test suite — coverage isn't just "does a test exist,"
it's "does it still fire when combined with everything else that can go wrong."

Reproduce: `python tests/defect_injection_eval.py`, then `dbt run && dbt test` from `dbt_project/`.
Reset: `python warehouse/load_raw.py` (raw is always rebuilt from the untouched source JSON files).

## Project layout

- `extractors/` — Python scripts that pull raw data from source APIs and land it,
  partitioned by date, immutably.
- `dbt_project/` — dbt models: staging (clean/typed) -> intermediate (business logic,
  e.g. FX conversion) -> marts (reporting-ready tables), plus data-quality tests.
- `dags/` — Airflow DAG(s) orchestrating extract -> load -> dbt run -> dbt test.
- `tests/` — Python unit tests (extractors, FX math, SQL validator).
- `docs/` — system-design.md and runbook.md.
