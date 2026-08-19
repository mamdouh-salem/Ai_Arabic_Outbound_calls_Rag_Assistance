"""Decides the final call outcome and generates a short Arabic summary of
what happened on the call — the actual content behind the architecture
diagram's "First Call Resolutions" report, not just a status flag.
"""
from __future__ import annotations

import asyncio
from typing import Literal

from outbound_ai.common.conversation import transcript_to_text
from outbound_ai.common.local_llm import run_chat
from outbound_ai.config.settings import get_settings

CallOutcome = Literal["resolved", "escalated", "unresolved"]

_SUMMARY_SYSTEM_PROMPT = """أنت تكتب ملخصًا موجزًا لمكالمة خدمة عملاء بناءً على نص المحادثة.
اكتب ملخصًا من جملتين إلى ثلاث جمل باللغة العربية الفصحى يوضح:
- المشكلة التي أبلغ عنها العميل
- ما تم فعله أو اقتراحه لحلها
- الحالة النهائية للمكالمة
لا تكتب أي مقدمات أو عناوين، فقط الملخص مباشرة."""


def _decide_outcome(state: dict) -> CallOutcome:
    """Escalation always wins (a human took over, full stop). Otherwise the
    call counts as resolved if either the customer confirmed it themselves
    (intent == "resolved") or the KB successfully answered it — checking
    only intent here was the bug that reported successful KB resolutions as
    "unresolved" (see graph/nodes.py history)."""
    if state.get("escalated"):
        return "escalated"
    if state.get("intent") == "resolved" or state.get("kb_answer_given"):
        return "resolved"
    return "unresolved"


async def summarize(state: dict) -> dict:
    """Async entry point used by graph/nodes.py.

    Returns {"call_outcome": ..., "call_summary": ...}. The generation call
    is blocking, same reasoning as kb_assist/intent_classifier — offloaded
    via asyncio.to_thread rather than awaited directly.
    """
    outcome = _decide_outcome(state)

    transcript_text = transcript_to_text(state.get("transcript", []))
    if not transcript_text:
        return {"call_outcome": outcome, "call_summary": ""}

    messages = [
        {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
        {"role": "user", "content": transcript_text},
    ]

    settings = get_settings()
    summary = await asyncio.to_thread(
        run_chat,
        messages,
        max_new_tokens=settings.generation_max_new_tokens,
        temperature=0.3,
    )

    return {"call_outcome": outcome, "call_summary": summary}
