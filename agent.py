"""
Text-to-SQL Agent for the Apartment Portfolio Database.

Ask a question in plain English -> the agent asks an LLM to translate it
into a SQLite SELECT query -> executes it -> if it errors, feeds the error
back to the LLM to self-correct (up to MAX_RETRIES times) -> once it runs
successfully, asks the LLM to explain the result in plain English.

Safety: only SELECT/WITH statements are ever allowed to execute. Anything
else (INSERT/UPDATE/DELETE/DROP/ALTER/ATTACH/PRAGMA/...) is rejected before
it ever reaches the database.

Run:  python3 agent.py
"""
import os
import re
import sqlite3
import sys

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()  # reads OPENAI_API_KEY from a local .env file

DB_PATH = "apartment_portfolio.db"
MODEL = "gpt-4o-mini"
MAX_RETRIES = 3

# Statement types we will execute. Everything else is refused up front.
ALLOWED_START = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)
FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|DETACH|PRAGMA|VACUUM|REPLACE)\b",
    re.IGNORECASE,
)


def get_schema_text(conn: sqlite3.Connection) -> str:
    """Pull the live CREATE TABLE statements straight from the database,
    so the model always sees the schema that's actually there."""
    rows = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL"
    ).fetchall()
    return "\n\n".join(r[0] for r in rows)


def is_safe_select(sql: str) -> tuple[bool, str]:
    """Guardrail: only a single read-only SELECT/WITH statement is allowed."""
    stripped = sql.strip().rstrip(";")
    if ";" in stripped:
        return False, "Only a single statement is allowed (no ';' inside the query)."
    if not ALLOWED_START.match(stripped):
        return False, "Only SELECT/WITH queries are allowed."
    if FORBIDDEN.search(stripped):
        return False, "Query contains a disallowed keyword (write/DDL operation)."
    return True, ""


def extract_sql(text: str) -> str:
    """Pull SQL out of a possible ```sql ... ``` fence; else return as-is."""
    m = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    return (m.group(1) if m else text).strip()


def build_system_prompt(schema: str) -> str:
    return f"""You are a SQLite expert helping a property-management analyst.
Given the database schema below, translate the user's question into a single
read-only SQLite SELECT query. Output ONLY the SQL inside a ```sql code block,
nothing else — no explanation.

When a question is about a specific property, tenant, or technician, JOIN to
the relevant name column (e.g. PROPERTY.PropertyName, TECHNICIAN.TechnicianName)
instead of returning only its numeric ID — a human-readable name is a more
useful answer than an internal ID.

Schema:
{schema}
"""


def call_model_for_sql(client: OpenAI, messages: list[dict]) -> str:
    """messages is the FULL running conversation (system + question +
    any prior attempt/error turns) — nothing is re-appended here, so each
    retry's correction instruction is genuinely the latest turn the model sees."""
    resp = client.chat.completions.create(model=MODEL, messages=messages, temperature=0)
    return extract_sql(resp.choices[0].message.content)


def ask_model_to_explain(client: OpenAI, question: str, sql: str,
                          columns: list[str], rows: list[tuple]) -> str:
    preview = rows[:15]
    prompt = f"""The user asked: "{question}"

This SQL was run:
{sql}

Columns: {columns}
Result rows (up to 15 shown): {preview}
Total rows returned: {len(rows)}

Write a short, clear natural-language answer to the user's question based on
this result. Mention concrete numbers. Do not mention SQL or the query itself.
"""
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()


def run_agent(client: OpenAI, conn: sqlite3.Connection, schema: str, question: str) -> dict:
    """Core agent loop, UI-agnostic. Returns a structured result instead of
    printing, so both the CLI (answer_question) and the Streamlit app
    (app.py) can render it however they like:

    {
      "success": bool,
      "sql": str | None,          # the SQL that finally succeeded
      "columns": list[str],
      "rows": list[tuple],
      "answer": str,               # natural-language answer (or failure message)
      "trace": [                   # every attempt, in order, for transparency
          {"attempt": int, "sql": str, "status": "blocked"|"error"|"ok", "detail": str|None}
      ],
    }
    """
    trace: list[dict] = []
    messages = [{"role": "system", "content": build_system_prompt(schema)},
                {"role": "user", "content": question}]
    sql = call_model_for_sql(client, messages)

    for attempt in range(1, MAX_RETRIES + 1):
        safe, reason = is_safe_select(sql)
        if not safe:
            trace.append({"attempt": attempt, "sql": sql, "status": "blocked", "detail": reason})
            messages += [{"role": "assistant", "content": f"```sql\n{sql}\n```"},
                         {"role": "user", "content": f"That query was rejected: {reason}. "
                                                       f"Provide a corrected read-only SELECT query."}]
            sql = call_model_for_sql(client, messages)
            continue
        try:
            cur = conn.execute(sql)
            cols = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchall()
            trace.append({"attempt": attempt, "sql": sql, "status": "ok", "detail": None})
            answer = ask_model_to_explain(client, question, sql, cols, rows)
            # If an earlier attempt was blocked by the safety guardrail (e.g. the
            # question asked for a DELETE/UPDATE), the model may have quietly
            # pivoted to an unrelated *read-only* question instead of refusing
            # outright — nothing unsafe ever ran, but silently answering a
            # different question is confusing UX. Make that visible.
            was_blocked = any(t["status"] == "blocked" for t in trace)
            if was_blocked:
                answer = ("Note: your request appeared to require modifying the "
                           "database (insert/update/delete), which this read-only "
                           "agent cannot do. I ran a related read-only query "
                           "instead:\n\n" + answer)
            return {"success": True, "sql": sql, "columns": cols, "rows": rows,
                    "answer": answer, "trace": trace}
        except sqlite3.Error as e:
            trace.append({"attempt": attempt, "sql": sql, "status": "error", "detail": str(e)})
            messages += [{"role": "assistant", "content": f"```sql\n{sql}\n```"},
                         {"role": "user", "content": f"That query failed with error: {e}. "
                                                       f"Fix it and return a corrected read-only SELECT query."}]
            sql = call_model_for_sql(client, messages)

    return {"success": False, "sql": None, "columns": [], "rows": [],
            "answer": "Sorry, I couldn't produce a working query after several attempts.",
            "trace": trace}


def answer_question(client: OpenAI, conn: sqlite3.Connection, schema: str, question: str) -> None:
    """CLI wrapper around run_agent() — prints the same output as before."""
    result = run_agent(client, conn, schema, question)
    for t in result["trace"]:
        if t["status"] == "blocked":
            print(f"  [blocked attempt {t['attempt']}] {t['detail']}\n  SQL was: {t['sql']}")
        elif t["status"] == "error":
            print(f"  [attempt {t['attempt']} failed] {t['detail']}\n  SQL was: {t['sql']}")
        elif t["status"] == "ok":
            print(f"  [SQL used]\n  {t['sql']}\n")
    print(f"  [Answer]\n  {result['answer']}\n")


def main():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("No OPENAI_API_KEY found. Create a .env file in this folder with:\n"
              "  OPENAI_API_KEY=sk-...\n")
        sys.exit(1)

    if not os.path.exists(DB_PATH):
        print(f"{DB_PATH} not found — run seed_data.py first.")
        sys.exit(1)

    client = OpenAI(api_key=api_key)
    conn = sqlite3.connect(DB_PATH)
    schema = get_schema_text(conn)

    print("Apartment Portfolio AI Agent — ask a question in plain English.")
    print("Examples:")
    print("  - Which property has the lowest occupancy rate?")
    print("  - Who are the top 3 technicians by completed maintenance requests?")
    print("  - How many leases are expiring in the next 60 days?")
    print("Type 'quit' to exit.\n")

    while True:
        question = input("You: ").strip()
        if question.lower() in ("quit", "exit"):
            break
        if not question:
            continue
        answer_question(client, conn, schema, question)

    conn.close()


if __name__ == "__main__":
    main()
