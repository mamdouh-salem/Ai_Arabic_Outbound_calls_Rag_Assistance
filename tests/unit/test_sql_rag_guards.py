"""Guard tests for the NL->SQL layer (rag/sql_rag.py).

validate_sql() is the only thing standing between an LLM-authored string and
the production database, so it gets adversarial coverage here. Everything in
this module is pure: no LLM, no database, no network.

Passing tests document guards that hold. xfail(strict=True) tests document
gaps that are still open -- they flip to failures the moment someone closes
them, which is the point.
"""
from __future__ import annotations

import re

import pytest

from outbound_ai.rag.sql_rag import validate_sql

# A real trailing LIMIT with a numeric argument, not the substring "limit".
_REAL_LIMIT = re.compile(r"\blimit\s+(\d+)\s*$", re.IGNORECASE)


# --------------------------------------------------------------------------
# Guards that hold
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE customers",
        "DELETE FROM tickets",
        "UPDATE calls SET call_outcome = 'resolved'",
        "INSERT INTO users (email) VALUES ('x@y.z')",
        "TRUNCATE calls",
        "GRANT ALL ON customers TO public",
        "ALTER TABLE calls ADD COLUMN x text",
    ],
)
def test_non_select_statements_rejected(sql: str) -> None:
    with pytest.raises(ValueError):
        validate_sql(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1; DROP TABLE customers",
        "SELECT * FROM calls; TRUNCATE calls",
        "SELECT 1;SELECT 2",
    ],
)
def test_stacked_statements_rejected(sql: str) -> None:
    """Statement stacking via ';' must not survive validation."""
    with pytest.raises(ValueError, match="Multiple statements|Forbidden"):
        validate_sql(sql)


def test_trailing_semicolon_is_tolerated() -> None:
    """A single trailing ';' is stripped, not treated as stacking."""
    assert validate_sql("SELECT id FROM customers;").lower().startswith("select")


def test_markdown_fences_are_stripped() -> None:
    out = validate_sql("```sql\nSELECT id FROM customers\n```")
    assert out.lower().startswith("select")
    assert "```" not in out


def test_plain_select_gets_a_limit_appended() -> None:
    out = validate_sql("SELECT id FROM customers")
    assert _REAL_LIMIT.search(out)


def test_case_insensitive_keyword_matching() -> None:
    with pytest.raises(ValueError):
        validate_sql("SeLeCt 1; DrOp TaBlE customers")


# --------------------------------------------------------------------------
# Open gaps
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM calls WHERE transcript ILIKE '%limit%'",
        "SELECT * FROM customers -- limit",
        "SELECT * FROM tickets WHERE title = 'no limit'",
    ],
)
@pytest.mark.xfail(
    reason="LIMIT enforcement is a naive substring test: the word 'limit' "
           "inside a string literal or comment skips the forced LIMIT, so "
           "the query runs unbounded",
    strict=True,
)
def test_limit_cannot_be_bypassed_by_substring(sql: str) -> None:
    assert _REAL_LIMIT.search(validate_sql(sql))


@pytest.mark.xfail(
    reason="the 'LIMIT <= 200' rule exists only in the system prompt; "
           "validate_sql never checks the number",
    strict=True,
)
def test_oversized_limit_is_clamped() -> None:
    out = validate_sql("SELECT * FROM calls LIMIT 100000")
    match = _REAL_LIMIT.search(out)
    assert match and int(match.group(1)) <= 200


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT id, name FROM customers",
        "SELECT * FROM knowledge_base_chunks",
        "SELECT transcript FROM calls",
    ],
)
@pytest.mark.xfail(
    reason="no workspace_id predicate is required or injected, so a "
           "generated query can read across every tenant -- this path "
           "bypasses the RLS relied on elsewhere",
    strict=True,
)
def test_workspace_scoping_is_enforced(sql: str) -> None:
    assert "workspace_id" in validate_sql(sql).lower()


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM tickets WHERE description ILIKE '%update%'",
        "SELECT * FROM tickets WHERE title ILIKE '%create%'",
    ],
)
@pytest.mark.xfail(
    reason="forbidden keywords are matched against the whole statement "
           "including string literals, so legitimate searches for words "
           "like 'update' are rejected",
    strict=True,
)
def test_keywords_inside_string_literals_are_allowed(sql: str) -> None:
    assert validate_sql(sql).lower().startswith("select")


@pytest.mark.xfail(
    reason="CTEs are rejected because validation requires the statement to "
           "start with SELECT; read-only WITH ... SELECT is legitimate",
    strict=True,
)
def test_cte_select_is_allowed() -> None:
    assert validate_sql("WITH t AS (SELECT 1 AS n) SELECT n FROM t")


def test_pg_sleep_passes_validation() -> None:
    """Documented, not a failure: resource exhaustion is handled by the
    10s statement_timeout at execution time, not by validate_sql."""
    assert validate_sql("SELECT pg_sleep(30)").lower().startswith("select")
