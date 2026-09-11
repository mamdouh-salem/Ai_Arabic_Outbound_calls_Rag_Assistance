"""Call outcome + post-KB routing tests.

Context: the committed call_reports.jsonl showed four calls with
intent="unresolved", a KB answer that was actually the grounding fallback
("لا تتوفر لدي معلومات كافية... سيتم تحويلك"), escalated=false, and
call_outcome="resolved".

_decide_outcome has since been fixed to ignore kb_answer_given. These tests
pin that fix, and document the part of the same bug that is still open in
graph/edges.route_after_kb.

Pure logic: no LLM, no database, no network.
"""
from __future__ import annotations

import pytest

from outbound_ai.agents.reporting import _decide_outcome
from outbound_ai.graph.edges import route_after_kb, route_on_intent

FALLBACK_AR = "لا تتوفر لدي معلومات كافية للإجابة على هذا السؤال، سيتم تحويلك إلى أحد ممثلي خدمة العملاء."


# --------------------------------------------------------------------------
# _decide_outcome — the original regression
# --------------------------------------------------------------------------

def test_unresolved_with_kb_answer_is_not_resolved() -> None:
    """The exact shape of the four bad rows in call_reports.jsonl."""
    state = {
        "intent": "unresolved",
        "kb_answer_given": True,
        "escalated": False,
    }
    assert _decide_outcome(state) == "unresolved"


def test_kb_answer_alone_never_resolves() -> None:
    """KB assistance is not customer confirmation."""
    for intent in ("unresolved", "unclear", "wants_human", None):
        assert _decide_outcome({"intent": intent, "kb_answer_given": True}) != "resolved"


def test_only_customer_confirmation_resolves() -> None:
    assert _decide_outcome({"intent": "resolved"}) == "resolved"


def test_escalation_wins_over_everything() -> None:
    assert _decide_outcome({"intent": "resolved", "escalated": True}) == "escalated"


def test_empty_state_defaults_to_unresolved() -> None:
    """Absent signal must not read as success — FCR should never be
    inflated by missing data."""
    assert _decide_outcome({}) == "unresolved"


@pytest.mark.parametrize(
    "state",
    [
        {"intent": "unresolved", "kb_answer_given": True, "escalated": False},
        {"intent": "unclear", "kb_answer_given": True, "escalated": False},
        {"intent": None, "kb_answer_given": True, "escalated": False},
    ],
)
def test_outcome_is_always_a_valid_label(state: dict) -> None:
    assert _decide_outcome(state) in {"resolved", "escalated", "unresolved"}


# --------------------------------------------------------------------------
# route_on_intent
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "intent, expected",
    [
        ("resolved", "resolved"),
        ("wants_human", "wants_human"),
        ("unresolved", "unresolved"),
        ("unclear", "unresolved"),
        (None, "unresolved"),
    ],
)
def test_route_on_intent(intent, expected: str) -> None:
    assert route_on_intent({"intent": intent}) == expected


# --------------------------------------------------------------------------
# route_after_kb — still open
# --------------------------------------------------------------------------

def test_route_after_kb_hands_off_when_no_answer() -> None:
    assert route_after_kb({"kb_answer_given": False}) == "handoff"


@pytest.mark.xfail(
    reason="route_after_kb trusts kb_answer_given, but that flag is True "
           "even when the KB returned the grounding fallback that promises "
           "a human transfer. The call routes to reporting instead of "
           "routing, so escalated is never set and no handoff is created -- "
           "this is why the logged calls show escalated=false alongside a "
           "transfer promise in the answer text.",
    strict=True,
)
def test_fallback_answer_should_hand_off_not_resolve() -> None:
    state = {"kb_answer_given": True, "kb_answer": FALLBACK_AR}
    assert route_after_kb(state) == "handoff"


@pytest.mark.xfail(
    reason="route_after_kb returns 'resolved' on the KB's own say-so "
           "without ever re-asking the customer. This contradicts "
           "_decide_outcome's stated principle that KB assistance is not "
           "resolution -- the edge did not get the fix the outcome "
           "function did.",
    strict=True,
)
def test_kb_answer_should_not_short_circuit_customer_confirmation() -> None:
    state = {"kb_answer_given": True, "intent": "unresolved"}
    assert route_after_kb(state) != "resolved"
