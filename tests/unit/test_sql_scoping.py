"""Unit tests for NL→SQL workspace scoping guard rails (pure logic)."""
from __future__ import annotations

import pytest

from outbound_ai.rag.sql_rag import ensure_workspace_scoped

WS = "6fd5448-4886-4a5b-939b-18764620abe3"


class TestWorkspaceScoping:
    def test_scoped_query_passes(self):
        sql = f"SELECT id FROM tickets WHERE workspace_id = '{WS}' LIMIT 10"
        assert ensure_workspace_scoped(sql, WS) == sql

    def test_unscoped_tenant_query_rejected(self):
        with pytest.raises(ValueError, match="workspace-scoped"):
            ensure_workspace_scoped("SELECT * FROM tickets LIMIT 10", WS)

    def test_all_workspaces_query_rejected(self):
        sql = "SELECT id FROM workspaces"
        with pytest.raises(ValueError, match="workspace-scoped"):
            ensure_workspace_scoped(sql, WS)

    def test_non_tenant_query_passes_unscoped(self):
        # harmless system query — no tenant rows involved
        assert ensure_workspace_scoped("SELECT now()", WS) == "SELECT now()"

    def test_join_query_with_filter_passes(self):
        sql = (
            "SELECT t.id FROM tickets t JOIN customers c ON c.id = t.customer_id "
            f"WHERE t.workspace_id = '{WS}' AND c.workspace_id = '{WS}' LIMIT 20"
        )
        assert ensure_workspace_scoped(sql, WS) == sql

    def test_join_query_missing_one_filter_rejected(self):
        sql = (
            "SELECT t.id FROM tickets t JOIN customers c ON c.id = t.customer_id "
            f"WHERE t.workspace_id = '{WS}' LIMIT 20"
        )
        with pytest.raises(ValueError):
            ensure_workspace_scoped(sql, WS)
