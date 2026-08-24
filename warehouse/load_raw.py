import sys
import duckdb

sys.stdout.reconfigure(encoding="utf-8")

DB_PATH = "warehouse/fx_reporting.duckdb"


def load_raw_tables() -> None:
    con = duckdb.connect(DB_PATH)

    con.sql("CREATE SCHEMA IF NOT EXISTS raw")

    con.sql("CREATE OR REPLACE TABLE raw.fx_rates AS SELECT * FROM read_json_auto('data/raw/fx_rates/date=*/rates.json')")

    con.sql("CREATE OR REPLACE TABLE raw.positions AS SELECT * FROM read_json_auto('data/raw/positions/date=*/positions.json')")

    con.close()


if __name__ == "__main__":
    load_raw_tables()

    con = duckdb.connect(DB_PATH)
    con.sql("SELECT * FROM raw.fx_rates").show()
    con.sql("SELECT * FROM raw.positions").show()
