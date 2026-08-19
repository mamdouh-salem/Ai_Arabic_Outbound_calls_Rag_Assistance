"""Decides escalation priority and writes the handoff brief for the human
CSR who takes over the call — the "priority + escalation + RAG brief" step
from the architecture diagram's Routing Agent. Reuses the same shared LLM
call as every other agent (common/local_llm.py).
"""
from __future__ import annotations

import asyncio
from typing import Literal

from outbound_ai.common.conversation import transcript_to_text
from outbound_ai.common.local_llm import run_chat
from outbound_ai.config.settings import get_settings

EscalationReason = Literal["customer_requested_human", "kb_could_not_resolve", "unresolved"]
Priority = Literal["low", "medium", "high"]

_BRIEF_SYSTEM_PROMPT = """أنت تكتب موجزًا سريعًا لموظف خدمة عملاء بشري سيتولى المكالمة الآن.
بناءً على نص المحادثة والمعلومات المتاحة، اكتب موجزًا من جملتين إلى ثلاث جمل باللغة العربية الفصحى يوضح:
- من هو العميل وما مشكلته
- ما الذي تمت تجربته حتى الآن (إن وجد)
- سبب تحويل المكالمة إليه الآن
لا تكتب أي مقدمات أو عناوين، فقط الموجز مباشرة."""


def _decide_reason(state: dict) -> EscalationReason:
    """Mirrors the graph's own routing logic (graph/edges.py) so the reason
    reported here always matches why the graph actually took this edge:
    wants_human skips kb_assist entirely, so kb_answer_given being False in
    that path doesn't mean the KB failed — the customer just asked for a
    human before it ever ran."""
    if state.get("intent") == "wants_human":
        return "customer_requested_human"
    if not state.get("kb_answer_given"):
        return "kb_could_not_resolve"
    return "unresolved"


def _decide_priority(reason: EscalationReason) -> Priority:
    # A customer who explicitly asked for a human is treated as higher
    # priority than one who's simply still stuck after KB help failed.
    return "high" if reason == "customer_requested_human" else "medium"


async def escalate(state: dict) -> dict:
    """Async entry point used by graph/nodes.py.

    Returns {"escalated": True, "escalation_reason": ..., "escalation_priority": ...,
    "escalation_brief": ...}. The generation call is blocking, same reasoning as
    every other agent — offloaded via asyncio.to_thread.
    """
    reason = _decide_reason(state)
    priority = _decide_priority(reason)

    context_lines = [
        f"رقم التذكرة: {state.get('ticket_id', '')}",
        f"التصنيف: {state.get('kb_category', '')}",
        f"سبب التحويل: {reason}",
    ]
    transcript_text = transcript_to_text(state.get("transcript", []))
    if transcript_text:
        context_lines.append("نص المحادثة:")
        context_lines.append(transcript_text)

    messages = [
        {"role": "system", "content": _BRIEF_SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(context_lines)},
    ]

    settings = get_settings()
    brief = await asyncio.to_thread(
        run_chat,
        messages,
        max_new_tokens=settings.generation_max_new_tokens,
        temperature=0.3,
    )

    return {
        "escalated": True,
        "escalation_reason": reason,
        "escalation_priority": priority,
        "escalation_brief": brief,
    }
