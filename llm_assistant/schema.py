import duckdb

DB_PATH = "warehouse/fx_reporting.duckdb"


def get_marts_schema_description() -> str:
    """Introspects the marts schema directly from DuckDB (read-only) and returns
    a text description for the LLM prompt. Generated from the real database, not
    hand-typed, so it can never silently drift out of sync with reality."""
    con = duckdb.connect(DB_PATH, read_only=True)
    rows = con.sql("""
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'marts'
        ORDER BY table_name, ordinal_position
    """).fetchall()
    con.close()

    tables: dict[str, list[str]] = {}
    for table_name, column_name, data_type in rows:
        tables.setdefault(table_name, []).append(f"{column_name} {data_type}")

    lines = []
    for table_name, columns in tables.items():
        lines.append(f"marts.{table_name}(")
        for col in columns:
            lines.append(f"    {col},")
        lines.append(")")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    print(get_marts_schema_description())
