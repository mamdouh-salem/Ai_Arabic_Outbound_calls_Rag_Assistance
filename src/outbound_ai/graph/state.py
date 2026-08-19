"""Shared state schema passed between every node in the LangGraph workflow."""
from __future__ import annotations

from typing import Literal, TypedDict

from langgraph.graph.message import add_messages
from typing_extensions import Annotated


class RetrievedChunk(TypedDict):
    id: str
    content: str
    source: str
    score: float


class GraphState(TypedDict):
    # ticket context, set once at graph entry
    ticket_id: str
    customer_id: str
    customer_phone: str
    kb_category: str

    # conversation so far — add_messages appends rather than overwrites
    transcript: Annotated[list, add_messages]

    # set by intent_classifier_node
    intent: Literal["resolved", "unresolved", "unclear", "wants_human"] | None

    # set by kb_assist_node
    retrieved_chunks: list[RetrievedChunk]
    kb_answer_given: bool

    # set by routing_node
    escalated: bool
    escalation_reason: str | None
    escalation_priority: str | None
    escalation_brief: str | None

    # set by reporting_node
    call_outcome: Literal["resolved", "escalated", "unresolved"] | None
    call_summary: str | None
