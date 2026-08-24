"""Unit tests for RAG personas + NL→SQL guard rails (pure logic, no DB/LLM)."""
from __future__ import annotations

import pytest

from outbound_ai.prompts.rag_prompt import (
    LANGUAGES,
    PERSONAS,
    PERSONA_NAMES,
    build_messages,
)
from outbound_ai.rag.sql_rag import validate_sql


# ---------------------------------------------------------------------------
# personas
# ---------------------------------------------------------------------------

class TestPersonas:
    def test_six_personas_registered(self):
        assert set(PERSONA_NAMES) == {
            "default", "egyptian_friendly", "formal",
            "concise", "empathetic", "technical",
        }
        assert len(set(PERSONAS.values())) == 6  # all distinct prompts

    def test_persona_changes_system_prompt(self):
        m = build_messages("سؤال", "سياق", persona="egyptian_friendly")
        assert "المصري" in m[0]["content"]

    def test_unknown_persona_falls_back_to_default(self):
        m = build_messages("q", "c", persona="does_not_exist")
        assert m[0]["content"] == PERSONAS["default"]

    def test_default_persona_is_msa_support(self):
        m = build_messages("q", "c")
        assert "مساعد دعم" in m[0]["content"]

    def test_user_template_still_receives_context_and_question(self):
        m = build_messages("السؤال", "السياق")
        assert "السؤال" in m[1]["content"]
        assert "السياق" in m[1]["content"]


# ---------------------------------------------------------------------------
# response language
# ---------------------------------------------------------------------------

class TestResponseLanguage:
    def test_five_languages_registered(self):
        assert set(LANGUAGES) == {"arabic", "english", "spanish", "german", "french"}

    def test_language_instruction_appended(self):
        m = build_messages("q", "c", persona="formal", language="spanish")
        assert "Spanish" in m[0]["content"]
        assert "فصحى" in m[0]["content"]  # persona prompt preserved

    def test_arabic_adds_no_instruction(self):
        m = build_messages("q", "c", language="arabic")
        assert "LANGUAGE REQUIREMENT" not in m[0]["content"]

    def test_unknown_language_ignored(self):
        m = build_messages("q", "c", language="klingon")
        assert "LANGUAGE REQUIREMENT" not in m[0]["content"]

    def test_citation_markers_kept_in_instruction(self):
        m = build_messages("q", "c", language="german")
        assert "[1]" in m[0]["content"]


# ---------------------------------------------------------------------------
# SQL guard rails
# ---------------------------------------------------------------------------

class TestSqlGuard:
    def test_plain_select_passes_and_gets_limit(self):
        sql = validate_sql("SELECT id, title FROM tickets")
        assert sql.lower().endswith("limit 50")
        assert sql.upper().startswith("SELECT")

    def test_existing_limit_not_duplicated(self):
        sql = validate_sql("SELECT id FROM calls LIMIT 10")
        assert sql.lower().count("limit") == 1

    def test_markdown_fences_stripped(self):
        sql = validate_sql("```sql\nSELECT id FROM tickets LIMIT 5\n```")
        assert sql == "SELECT id FROM tickets LIMIT 5"

    @pytest.mark.parametrize("bad", [
        "INSERT INTO tickets (title) VALUES ('x')",
        "UPDATE tickets SET status='x'",
        "DELETE FROM tickets",
        "DROP TABLE tickets",
        "ALTER TABLE tickets ADD COLUMN x int",
        "TRUNCATE tickets",
        "GRANT ALL ON tickets TO anon",
    ])
    def test_forbidden_statements_rejected(self, bad):
        with pytest.raises(ValueError):
            validate_sql(bad)

    def test_multi_statement_rejected(self):
        with pytest.raises(ValueError):
            validate_sql("SELECT 1; DROP TABLE tickets")

    def test_keyword_inside_string_is_not_flagged(self):
        # the word 'created' contains 'create' — must NOT be rejected
        sql = validate_sql(
            "SELECT created_at FROM tickets WHERE title ILIKE '%created%' LIMIT 3"
        )
        assert "created_at" in sql
