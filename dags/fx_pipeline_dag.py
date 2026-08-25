from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator


def alert_on_failure(context) -> None:
    """Minimal failure alert: logs a structured line Airflow's own logging captures.
    Swap for a Slack webhook call once one exists -- kept simple and dependency-free here."""
    task_id = context["task_instance"].task_id
    run_date = context["ds"]
    print(f"ALERT: task '{task_id}' failed for run date {run_date}")


default_args = {
    "owner": "fx_reporting",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "on_failure_callback": alert_on_failure,
}

with DAG(
    dag_id="fx_reporting_pipeline",
    default_args=default_args,
    description="Extract FX rates + positions, load to DuckDB, run dbt models and tests.",
    schedule="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
) as dag:

    extract_fx_rates = BashOperator(
        task_id="extract_fx_rates",
        bash_command="cd /opt/project && python extractors/fx_rates.py",
    )

    extract_positions = BashOperator(
        task_id="extract_positions",
        bash_command="cd /opt/project && python extractors/positions.py",
    )

    load_raw = BashOperator(
        task_id="load_raw",
        bash_command="cd /opt/project && python warehouse/load_raw.py",
    )

    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command="cd /opt/project/dbt_project && dbt run --profiles-dir .",
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command="cd /opt/project/dbt_project && dbt test --profiles-dir .",
    )

    # Extraction can run in parallel (independent sources); loading needs both to finish
    # first; dbt run needs raw loaded; dbt test gates anything downstream ever treating
    # the marts as "published" -- a test failure here stops the DAG, so bad data never
    # reaches a report.
    [extract_fx_rates, extract_positions] >> load_raw >> dbt_run >> dbt_test
