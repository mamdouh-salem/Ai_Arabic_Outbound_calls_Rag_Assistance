"""Natural-language → SQL over the business database (read-only).

The manager-requested "structured data sources" capability: an authenticated
admin asks a question in plain Arabic/English, the LLM writes a SELECT against
the known public schema, we validate it hard (SELECT-only, single statement,
forbidden keywords, forced LIMIT), execute it READ-ONLY with a statement
timeout, and return rows + the generated SQL.

TENANT SCOPING (the "give me all workspaces/users" hole):
  admins are FORCED into their own workspace — the prompt mandates a
  workspace_id filter AND a post-generation check rejects any query that
  touches a tenant table without the caller's workspace uuid. Super admins
  are unrestricted (platform-wide role).

Security posture:
  * endpoint is admin/super_admin only
  * read-only connection + statement_timeout at the DB level
  * no DDL/DML keywords anywhere in the statement
  * single statement only (no stacking via ';')
  * mandatory workspace filter for non-super roles (prompt + validator)
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

# tables that carry tenant rows — queries touching these MUST be scoped
_TENANT_TABLES = (
    "customers", "tickets", "calls", "knowledge_base_chunks",
    "workspace_members", "users", "workspaces",
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
    call_status text, ticket_ref text, workspace_id uuid)
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

_SCOPING_RULE = """
- MANDATORY TENANT FILTER: the caller may ONLY see rows belonging to
  workspace_id = '{workspace_id}'. Every table in the query that has a
  workspace_id column MUST include `workspace_id = '{workspace_id}'` in its
  WHERE clause (or JOIN condition). NEVER return rows from any other
  workspace, and never list other workspaces' ids, users or documents."""


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


def _touches_tenant_table(sql: str) -> bool:
    lowered = sql.lower()
    return any(re.search(rf"\b{t}\b", lowered) for t in _TENANT_TABLES)


def ensure_workspace_scoped(sql: str, workspace_id: str) -> str:
    """Reject tenant queries that don't carry the caller's workspace filter.

    Rule: every tenant table referenced in the query must be accompanied by a
    workspace_id filter — a JOIN across two tenant tables with a single filter
    would still leak the other table's cross-workspace rows."""
    lowered = sql.lower()
    if not _touches_tenant_table(sql):
        return sql  # e.g. SELECT now() — harmless
    if workspace_id.lower() not in lowered:
        raise ValueError(
            "Query is not workspace-scoped: it must filter by "
            f"workspace_id = '{workspace_id}'."
        )
    tenant_tables = [t for t in _TENANT_TABLES if re.search(rf"\b{t}\b", lowered)]
    filter_count = len(re.findall(r"workspace_id", lowered))
    if filter_count < len(tenant_tables):
        raise ValueError(
            f"Query references {len(tenant_tables)} tenant table(s) but has only "
            f"{filter_count} workspace_id filter(s). Add a workspace_id filter "
            "for every tenant table in the query."
        )
    return sql


def run_sql_query(question: str, workspace_id: str | None = None) -> dict:
    """NL question → {question, sql, rows, columns, row_count}. Blocking.

    workspace_id: when set (admin callers), the generated SQL is REQUIRED to
    filter by this workspace — enforced by prompt rule + post-generation
    validation, with one corrective retry before failing."""
    from outbound_ai.common.local_llm import run_chat

    settings = get_settings()
    system = _SQL_SYSTEM_PROMPT
    if workspace_id:
        system += _SCOPING_RULE.format(workspace_id=workspace_id)

    user_message = question
    last_sql = ""
    for attempt in (1, 2):  # one corrective retry, then reject
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ]
        raw = run_chat(messages, max_new_tokens=300, temperature=0.0)
        last_sql = raw
        try:
            sql = validate_sql(raw)
            if workspace_id:
                sql = ensure_workspace_scoped(sql, workspace_id)
            break
        except ValueError as exc:
            if attempt == 2:
                raise ValueError(
                    f"Could not produce a compliant query: {exc}"
                ) from exc
            # corrective retry
            user_message = (
                f"{question}\n\nYour previous query was rejected: {exc}\n"
                f"Previous query: {_strip_fences(raw)}\n"
                "Regenerate a single SELECT that fixes this."
            )
    else:
        raise ValueError("Could not produce a compliant query.")

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
    log.info("sql_query_executed", rows=len(rows_out),
             workspace_scoped=bool(workspace_id))
    return {"question": question, "sql": sql,
            "columns": columns, "rows": rows_out, "row_count": len(rows_out)}
