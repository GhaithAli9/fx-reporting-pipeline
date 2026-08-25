import re

import anthropic
import duckdb
from dotenv import load_dotenv

from llm_assistant.schema import get_marts_schema_description
from llm_assistant.validator import ValidationError, validate_sql

load_dotenv()

DB_PATH = "warehouse/fx_reporting.duckdb"
MODEL = "claude-opus-5"


def build_system_prompt() -> str:
    schema = get_marts_schema_description()
    return f"""You are a SQL assistant for a financial reporting database (FX position valuations).

You can ONLY query these tables:

{schema}
Rules:
- Respond with ONLY a single SQL SELECT statement targeting the tables above. No explanation, no markdown formatting, no code fences, no commentary.
- Never use INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, or ATTACH.
- If the question cannot be answered using only the tables above, respond with exactly: CANNOT_ANSWER
"""


def _extract_sql(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:sql)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()
    return text


def _call_claude(client: anthropic.Anthropic, system_prompt: str, messages: list) -> str:
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=system_prompt,
        messages=messages,
    )
    return "".join(block.text for block in response.content if block.type == "text")


def _try_execute(sql: str) -> dict:
    try:
        validated_sql = validate_sql(sql)
    except ValidationError as e:
        return {"rows": None, "error": f"Validation failed: {e}"}

    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        rel = con.sql(validated_sql)
        rows = [dict(zip(rel.columns, row)) for row in rel.fetchall()]
        con.close()
        return {"rows": rows, "error": None}
    except Exception as e:
        return {"rows": None, "error": f"Execution failed: {e}"}


def ask(question: str) -> dict:
    """Answers a natural-language question against the marts, safely.

    Returns: {question, sql, rows, refused, error}. `error` set with `rows`
    None means both the original attempt and the one repair attempt failed --
    never returns a guessed or partial answer.
    """
    client = anthropic.Anthropic()
    system_prompt = build_system_prompt()
    messages = [{"role": "user", "content": question}]

    raw = _call_claude(client, system_prompt, messages)

    if raw.strip() == "CANNOT_ANSWER":
        return {"question": question, "sql": None, "rows": None, "refused": True, "error": None}

    sql = _extract_sql(raw)
    result = _try_execute(sql)

    if result["error"] is None:
        return {"question": question, "sql": sql, "rows": result["rows"], "refused": False, "error": None}

    # One repair attempt: feed the actual error back and ask for a fix.
    messages.append({"role": "assistant", "content": raw})
    messages.append({
        "role": "user",
        "content": (
            f"That query failed with this error:\n{result['error']}\n"
            "Respond with ONLY a corrected SQL SELECT statement."
        ),
    })
    raw2 = _call_claude(client, system_prompt, messages)

    if raw2.strip() == "CANNOT_ANSWER":
        return {"question": question, "sql": sql, "rows": None, "refused": True, "error": result["error"]}

    sql2 = _extract_sql(raw2)
    result2 = _try_execute(sql2)

    return {
        "question": question,
        "sql": sql2,
        "rows": result2["rows"],
        "refused": False,
        "error": result2["error"],
    }


if __name__ == "__main__":
    import json

    for q in [
        "What is the total EUR exposure on 2024-01-15?",
        "What is the weather in Berlin today?",
    ]:
        print(f"\nQ: {q}")
        print(json.dumps(ask(q), indent=2, default=str))
