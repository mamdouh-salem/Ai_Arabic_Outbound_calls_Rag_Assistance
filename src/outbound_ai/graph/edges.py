"""Conditional edge functions — decide which node runs next based on state."""
from __future__ import annotations

from outbound_ai.graph.state import GraphState


def route_on_intent(state: GraphState) -> str:
    """After intent_classifier_node: where does the call go next?"""
    intent = state.get("intent")
    if intent == "resolved":
        return "resolved"
    if intent == "wants_human":
        return "wants_human"
    # "unresolved" or "unclear" both try the KB first
    return "unresolved"


def route_after_kb(state: GraphState) -> str:
    """After kb_assist_node: did the KB actually resolve it, or hand off?"""
    if state.get("kb_answer_given"):
        return "resolved"
    return "handoff"
