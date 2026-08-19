"""Classifies the customer's last turn into one of four intents.

Uses the same shared local LLM as rag/generation.py (see
common/local_llm.py) — a lightweight constrained prompt asking for a single
label word, rather than JSON/structured output, since the local transformers
stack here has no constrained-decoding library (outlines/guidance)
installed. Parsing falls back to "unclear" if the reply doesn't cleanly
match one of the four labels.
"""
from __future__ import annotations

import asyncio
import re
from typing import Literal

from outbound_ai.common.local_llm import run_chat

Intent = Literal["resolved", "unresolved", "unclear", "wants_human"]

_VALID_INTENTS: tuple[Intent, ...] = ("resolved", "unresolved", "unclear", "wants_human")

# --- REGEX SAFETY NET PATTERNS ---
# يمسك أي كلمة فيها جذر (حل) ومنتهية بـ (ش) زي: تحلتش، ماحلتش، اتحلتش، حلتش
_UNRESOLVED_REGEX = re.compile(r'\b\w*حل\w*ش\b')

# يمسك الكلمات الإيجابية الصريحة لجذر حل بدون ش في نهاية الكلمة
# يطابق: حليت، تحلت، اتحلت، حلينا، حلها، انحلت، اتفت السلسلة، إلخ.
_RESOLVED_REGEX = re.compile(r'\b\w*حل(يت|ت|نا|ها|ت|ّيت|ّت)\b')


_SYSTEM_PROMPT = """أنت مصنّف نوايا لمكالمات خدمة عملاء باللغة العربية.
اقرأ آخر رسالة من العميل وصنّفها إلى واحدة فقط من هذه الفئات:
- resolved: العميل يؤكد أن المشكلة تم حلها بالفعل.
- unresolved: العميل يذكر أن المشكلة ما زالت قائمة أو يصف مشكلة جديدة.
- unclear: رد العميل غامض أو غير مرتبط بالمشكلة أو غير مفهوم.
- wants_human: العميل يطلب صراحة التحدث إلى موظف بشري.
رد بكلمة واحدة فقط من الكلمات الأربع بالإنجليزية: resolved أو unresolved أو unclear أو wants_human. لا تكتب أي شيء آخر."""


def _last_human_text(transcript: list) -> str:
    """Handles both LangChain BaseMessage objects (what's actually in
    GraphState after add_messages converts them) and plain dicts (in case
    this is ever called before that conversion happens)."""
    for message in reversed(transcript):
        role = getattr(message, "type", None)
        if role is None and isinstance(message, dict):
            role = message.get("role")
        if role == "human":
            content = getattr(message, "content", None)
            if content is None and isinstance(message, dict):
                content = message.get("content", "")
            return content or ""
    return ""


def _parse_intent(raw: str) -> Intent:
    lowered = raw.strip().lower()
    for intent in _VALID_INTENTS:
        if re.search(rf"\b{re.escape(intent)}\b", lowered):
            return intent
    return "unclear"


async def classify(transcript: list) -> Intent:
    """Async entry point used by graph/nodes.py.

    The actual generation call is blocking (local GPU inference), so it's
    offloaded via asyncio.to_thread rather than blocking the event loop.
    """
    customer_text = _last_human_text(transcript)
    if not customer_text:
        return "unclear"

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": customer_text},
    ]

    # 1. تصنيف الـ LLM الأساسي
    raw = await asyncio.to_thread(run_chat, messages, max_new_tokens=200, temperature=0.0)
    llm_intent = _parse_intent(raw)

    # 2. الـ Safety Net / Sanity Check (تطبيق الـ Regex)
    
    # حالة الـ Unresolved: لو النص فيه "تحلتش/ماحلتش" صريحة، والـ LLM طلعها أي حاجة تانية (ما عدا طلب البشري)، بنجبرها تبقى unresolved
    if _UNRESOLVED_REGEX.search(customer_text):
        if llm_intent != "wants_human":  # لو العميل قال "ماحلتش عايز بني آدم" سيبها wants_human زي ما هي
            return "unresolved"

    # حالة الـ Resolved: لو النص فيه "حليت/اتحلت" صريحة ومفيش فيها "ش"، والـ LLM طلعها unresolved أو unclear
    elif _RESOLVED_REGEX.search(customer_text):
        if llm_intent in ("unresolved", "unclear"):
            return "resolved"

    # 3. لو مفيش أي تضارب أو الـ regex ملقطش حاجة، بنمشي ورا الـ LLM عادي
    return llm_intent
