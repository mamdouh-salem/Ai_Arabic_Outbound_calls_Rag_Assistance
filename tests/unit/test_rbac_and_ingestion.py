"""Unit tests for role-based data visibility filters + KB ingestion chunker.

Pure-logic tests — no DB, no network, no JWT verification.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from outbound_ai.api.routers.data import visible_call_filters, visible_ticket_filters
from outbound_ai.auth.models import AppRole, AuthContext
from outbound_ai.rag.ingestion import chunk_text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_ctx(role: AppRole) -> AuthContext:
    return AuthContext(
        user_id=uuid4(),
        workspace_id=uuid4(),
        role=role,
        email="test@example.com",
    )


# ---------------------------------------------------------------------------
# visible_ticket_filters
# ---------------------------------------------------------------------------

class TestTicketVisibility:
    def test_agent_sees_only_assigned(self):
        ctx = make_ctx(AppRole.agent)
        f = visible_ticket_filters(ctx)
        assert f == {
            "assigned_to": str(ctx.user_id),
            "workspace_id": str(ctx.workspace_id),
        }

    def test_admin_sees_whole_workspace(self):
        ctx = make_ctx(AppRole.admin)
        f = visible_ticket_filters(ctx)
        assert f == {"workspace_id": str(ctx.workspace_id)}
        assert "assigned_to" not in f

    def test_super_admin_without_header_sees_everything(self):
        ctx = AuthContext(
            user_id=uuid4(), workspace_id=None, role=AppRole.super_admin, email="s@e.com"
        )
        assert visible_ticket_filters(ctx) is None

    def test_super_admin_with_header_scopes_to_workspace(self):
        ctx = make_ctx(AppRole.super_admin)
        f = visible_ticket_filters(ctx)
        assert f == {"workspace_id": str(ctx.workspace_id)}

    def test_admin_without_workspace_raises(self):
        ctx = AuthContext(
            user_id=uuid4(), workspace_id=None, role=AppRole.admin, email="a@e.com"
        )
        with pytest.raises(ValueError):
            visible_ticket_filters(ctx)


# ---------------------------------------------------------------------------
# visible_call_filters
# ---------------------------------------------------------------------------

class TestCallVisibility:
    def test_agent_with_assigned_tickets_gets_id_list(self):
        ctx = make_ctx(AppRole.agent)
        ids = [str(uuid4()), str(uuid4())]
        f = visible_call_filters(ctx, fetch_assigned_ticket_ids=lambda: ids)
        assert f == {"ticket_id": ids}

    def test_agent_with_no_tickets_matches_nothing(self):
        ctx = make_ctx(AppRole.agent)
        f = visible_call_filters(ctx, fetch_assigned_ticket_ids=lambda: [])
        assert f == {"ticket_id": ["__none__"]}

    def test_admin_falls_back_to_workspace_rule(self):
        ctx = make_ctx(AppRole.admin)
        f = visible_call_filters(ctx, fetch_assigned_ticket_ids=lambda: [])
        assert f == {"workspace_id": str(ctx.workspace_id)}


# ---------------------------------------------------------------------------
# chunk_text
# ---------------------------------------------------------------------------

class TestChunkText:
    def test_empty_input_returns_no_chunks(self):
        assert chunk_text("") == []
        assert chunk_text("   \n\n  ") == []

    def test_short_text_single_chunk(self):
        chunks = chunk_text("مرحبا بالعالم", max_chars=100)
        assert len(chunks) == 1
        assert chunks[0] == "مرحبا بالعالم"

    def test_paragraphs_combined_under_cap(self):
        paras = ["p" * 50] * 6
        text = "\n\n".join(paras)
        chunks = chunk_text(text, max_chars=200, overlap=20)
        assert all(len(c) <= 200 for c in chunks)
        # everything survives
        assert sum(c.count("p") for c in chunks) >= 300

    def test_oversized_paragraph_hard_split(self):
        huge = "x" * 1000
        chunks = chunk_text(huge, max_chars=300, overlap=50)
        assert len(chunks) > 1
        assert all(len(c) <= 300 for c in chunks)

    def test_overlap_carries_tail_between_chunks(self):
        para_a, para_b = ("a" * 150), ("b" * 150)
        chunks = chunk_text(f"{para_a}\n\n{para_b}", max_chars=200, overlap=30)
        assert len(chunks) >= 2
        # second chunk starts with the tail of the previous one
        assert chunks[1].startswith(chunks[0][-30:])

    def test_arabic_text_preserved(self):
        text = "\n\n".join(["إصلاح الراوتر خطوة بخطوة"] * 10)
        chunks = chunk_text(text, max_chars=120)
        joined = " ".join(chunks)
        assert "الراوتر" in joined
