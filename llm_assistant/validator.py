import sqlglot
from sqlglot import exp

MAX_ROWS = 200
ALLOWED_SCHEMA = "marts"


class ValidationError(Exception):
    pass


def validate_sql(sql: str) -> str:
    """Validates that `sql` is a single, read-only SELECT statement scoped to
    the marts schema, and enforces a row LIMIT. Returns the SQL to actually
    execute (with the limit applied/capped), or raises ValidationError.

    This is layer one of two defenses -- layer two is that the DB connection
    executing this SQL is itself opened read-only (see assistant.py), so a
    bug here still can't produce a write.
    """
    try:
        statements = sqlglot.parse(sql, read="duckdb")
    except sqlglot.errors.ParseError as e:
        raise ValidationError(f"Could not parse SQL: {e}")

    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        raise ValidationError("Only a single SQL statement is allowed.")

    stmt = statements[0]
    if not isinstance(stmt, exp.Select):
        raise ValidationError(
            f"Only SELECT statements are allowed, got: {type(stmt).__name__}"
        )

    # Defense in depth: reject any write/DDL node anywhere in the tree, even
    # though a top-level non-Select is already rejected above (e.g. a CTE
    # smuggling a write wouldn't be caught by the isinstance check alone).
    forbidden = (
        exp.Insert, exp.Update, exp.Delete, exp.Drop,
        exp.Create, exp.Alter, exp.Attach,
    )
    for node in stmt.walk():
        if isinstance(node, forbidden):
            raise ValidationError(f"Disallowed statement type: {type(node).__name__}")

    for table in stmt.find_all(exp.Table):
        if table.db and table.db.lower() != ALLOWED_SCHEMA:
            raise ValidationError(
                f"Only the '{ALLOWED_SCHEMA}' schema is queryable, got: {table.db}"
            )

    existing_limit = stmt.args.get("limit")
    if existing_limit is None:
        stmt = stmt.limit(MAX_ROWS)
    else:
        value = int(existing_limit.expression.this)
        if value > MAX_ROWS:
            stmt.set("limit", exp.Limit(this=None, expression=exp.Literal.number(MAX_ROWS)))

    return stmt.sql(dialect="duckdb")
