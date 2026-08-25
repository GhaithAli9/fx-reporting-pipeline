import sys
import duckdb

sys.stdout.reconfigure(encoding="utf-8")

DB_PATH = "warehouse/fx_reporting.duckdb"


def inject_defects() -> None:
    """Corrupts raw tables with 4 realistic defects, to prove dbt tests catch them.
    Reset with: python warehouse/load_raw.py (rebuilds raw from the untouched JSON files).
    """
    con = duckdb.connect(DB_PATH)

    # Defect 1: null FX rate
    con.sql("""
        UPDATE raw.fx_rates
        SET rates = struct_pack(chf := rates.chf, gbp := rates.gbp, jpy := rates.jpy, usd := NULL)
        WHERE "date" = '2024-01-15'
    """)

    # Defect 2: duplicate position key
    con.sql("""
        INSERT INTO raw.positions
        SELECT * FROM raw.positions WHERE position_id = 'POS0000'
    """)

    # Defect 3: out-of-range value (negative amount)
    con.sql("""
        UPDATE raw.positions
        SET amount = -50000
        WHERE position_id = 'POS0001'
    """)

    # Defect 5 (defect 4, "stale date", is a freshness concern -- not injectable as a row,
    # see docs/system-design.md ADR-011): orphan position, no matching FX rate for its date
    con.sql("""
        INSERT INTO raw.positions
        VALUES ('POS9999', 'USD', 10000.0, '2024-01-16', '2024-01-16')
    """)

    con.close()
    print("4 defects injected into raw tables. Run:")
    print("  cd dbt_project && ../venv/Scripts/dbt.exe run --profiles-dir . && ../venv/Scripts/dbt.exe test --profiles-dir .")
    print("Reset afterward with: ./venv/Scripts/python.exe warehouse/load_raw.py")


if __name__ == "__main__":
    inject_defects()
