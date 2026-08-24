"""Natural-language → SQL over the business database (read-only).

The manager-requested "structured data sources" capability: an authenticated
admin asks a question in plain Arabic/English, the LLM writes a SELECT against
the known public schema, we validate it hard (SELECT-only, single statement,
forbidden keywords, forced LIMIT), execute it READ-ONLY with a statement
timeout, and return rows + the generated SQL.

Security posture:
  * endpoint is admin/super_admin only (data visibility rules apply upstream)
  * read-only connection + statement_timeout at the DB level, not just prompts
  * no DDL/DML keywords anywhere in the statement
  * single statement only (no stacking via ';')
"""
from __future__ import annotations

import re

import psycopg
import structlog

from outbound_ai.config.settings import get_settings

log = structlog.get_logger(__name__)

_FORBIDDEN = (
    "insert", "update", "delete", "drop", "alter", "create", "truncate",
    "grant", "revoke", "copy", "vacuum", "analyze", "call", "do", "set",
)

_SQL_SYSTEM_PROMPT = """You are a senior PostgreSQL engineer. Write ONE read-only
SELECT query that answers the user's question about this support-call platform.

Schema (public):
- customers(id uuid, name text, phone text, workspace_id uuid)
- tickets(id uuid, customer_id uuid->customers, title text, description text,
    status text, kb_category text, assigned_to uuid, workspace_id uuid)
- calls(id uuid, ticket_id uuid->tickets, vonage_call_id text, transcript text,
    intent text, kb_answer text, kb_answer_given bool, escalated bool,
    escalation_reason text, call_outcome text, call_summary text,
    started_at timestamptz, ended_at timestamptz, duration_seconds int,
    call_status text, workspace_id uuid, ticket_ref text)
- knowledge_base_chunks(id uuid, content text, metadata jsonb, workspace_id uuid)
- workspaces(id uuid, name text, slug text, plan text)
- users(id uuid, email text, display_name text, platform_role text)
- workspace_members(id uuid, workspace_id uuid, user_id uuid, role text)

Rules:
- Output ONLY the SQL — no explanations, no markdown fences.
- SELECT only. Single statement. No semicolon at the end.
- Always include a LIMIT (<= 200).
- Use Arabic-aware comparisons when the question is Arabic
  (e.g. ILIKE '%كلمة%'). Prefer readable column aliases."""


def _strip_fences(text: str) -> str:
    m = re.search(r"```(?:sql)?\s*(.+?)\s*```", text, re.S)
    return (m.group(1) if m else text).strip()


def validate_sql(sql: str) -> str:
    """Hard validation. Raises ValueError on anything but a single plain
    SELECT; enforces a LIMIT."""
    s = _strip_fences(sql).rstrip(";").strip()
    if not s.lower().startswith("select"):
        raise ValueError("Only SELECT queries are allowed.")
    if ";" in s:
        raise ValueError("Multiple statements are not allowed.")
    lowered = s.lower()
    for kw in _FORBIDDEN:
        if re.search(rf"\b{kw}\b", lowered):
            raise ValueError(f"Forbidden keyword: {kw}")
    if "limit" not in lowered:
        s += " LIMIT 50"
    return s


def run_sql_query(question: str) -> dict:
    """NL question → {question, sql, rows, columns, row_count}. Blocking."""
    from outbound_ai.common.local_llm import run_chat

    settings = get_settings()
    messages = [
        {"role": "system", "content": _SQL_SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    raw = run_chat(messages, max_new_tokens=300, temperature=0.0)
    sql = validate_sql(raw)

    conn_kwargs = {"autocommit": True}
    with psycopg.connect(
        settings.database_url.get_secret_value(),
        **conn_kwargs,
    ) as conn:
        conn.read_only = True  # psycopg3 attribute — DB rejects any write
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '10s'")
            cur.execute(sql)
            columns = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchall() if cur.description else []

    rows_out = [
        {col: (str(v) if hasattr(v, "isoformat") else v) for col, v in zip(columns, r)}
        for r in rows
    ]
    log.info("sql_query_executed", rows=len(rows_out))
    return {"question": question, "sql": sql,
            "columns": columns, "rows": rows_out, "row_count": len(rows_out)}
