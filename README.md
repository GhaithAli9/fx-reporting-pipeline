# fx-reporting-pipeline

An end-to-end ELT pipeline that ingests FX and position data, transforms it into
audit-ready reporting marts with dbt, enforces data-quality tests, and is designed to be
orchestrated with Airflow and queried by a schema-grounded LLM assistant.

## Status

**Built and verified, with real data at every step:**
- Two idempotent Python extractors (FX rates from a free live API, synthetic positions),
  landing date-partitioned raw JSON.
- DuckDB warehouse, loaded from raw JSON via dbt.
- dbt project: 2 staging models, 1 intermediate (point-in-time FX join), 2 marts
  (position-level detail + daily aggregate), 11 passing data-quality tests.
- A real defect-injection evaluation proving the tests catch bad data — see below.

- **Airflow**, running for real via Docker Compose (`LocalExecutor`, see `docs/system-design.md`
  ADR-012) — full DAG run proven end-to-end: `extract_fx_rates`, `extract_positions`,
  `load_raw`, `dbt_run`, `dbt_test` all reached `success` in Airflow's own task history.
- **CI** (`.github/workflows/ci.yml`) — runs the full extract/load/dbt pipeline on every
  push. Verified locally with `act` (simulates GitHub's Actions runners via Docker) before
  ever pushing — 5 models, 11 tests, passing inside a real simulated runner (ADR-013).

- **pytest unit tests** (`tests/test_fx_rates.py`, `tests/test_positions.py`) — 8 tests,
  mocked HTTP calls (no real network needed), idempotency and determinism checks. Wired into
  CI.

**Not started yet:** NL→SQL LLM assistant, Snowflake port, BI dashboard.

## How to run

**Manually:**
```bash
./venv/Scripts/python.exe extractors/fx_rates.py
./venv/Scripts/python.exe extractors/positions.py
./venv/Scripts/python.exe warehouse/load_raw.py
cd dbt_project
../venv/Scripts/dbt.exe run --profiles-dir .
../venv/Scripts/dbt.exe test --profiles-dir .
```

**Orchestrated (Airflow, via Docker):**
```bash
cd airflow_docker
docker compose up airflow-init   # first time only
docker compose up -d
# webserver at http://localhost:8081 (user: airflow / pass: airflow, local dev only)
```

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

- `extractors/` — Python scripts that pull raw data (FX rates, synthetic positions) and
  land it, partitioned by date, idempotently.
- `warehouse/` — loads raw JSON into DuckDB (`load_raw.py`) and holds the DuckDB file itself.
- `dbt_project/` — dbt models: staging (clean/typed) -> intermediate (point-in-time FX
  join) -> marts (reporting-ready tables), plus data-quality tests (`models/*/​_*.yml`,
  `tests/`).
- `dags/` — Airflow DAG orchestrating extract -> load -> dbt run -> dbt test (see Status).
- `tests/` — Python-level tests, including the real defect-injection evaluation.
- `docs/` — `system-design.md` (architecture decision log), `learning-log.md` (concepts and
  bugs, task by task), `runbook.md` (operational troubleshooting reference).
