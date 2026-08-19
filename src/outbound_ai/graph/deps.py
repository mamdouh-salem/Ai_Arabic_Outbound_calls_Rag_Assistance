"""
Runtime dependencies injected into graph nodes.

Node functions receive a GraphDependencies instance and never construct their
own STT/TTS/endpointing adapters or call Supabase directly — this is what lets
a fake adapter stand in during tests without touching graph or node code, same
principle as voice/base.py's port/adapter split.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from outbound_ai.voice.base import EndpointingPort, STTPort, TTSPort

# Placeholder until agents/kb_assist.py + the real rag pipeline are wired in.
# Takes (query_text, kb_category) and returns (answer_text, retrieved_chunks, kb_answer_given).
KBRetrieveFn = Callable[[str, str], Awaitable[tuple[str, list[dict], bool]]]

# Takes the transcript (list of BaseMessage) and returns one of
# "resolved" | "unresolved" | "unclear" | "wants_human".
IntentClassifyFn = Callable[[list], Awaitable[str]]

# Takes the full GraphState dict and returns {"call_outcome": ..., "call_summary": ...}.
ReportFn = Callable[[dict], Awaitable[dict]]

# Takes the full GraphState dict and returns {"escalated": True, "escalation_reason": ...,
# "escalation_priority": ..., "escalation_brief": ...}.
RouteFn = Callable[[dict], Awaitable[dict]]


@dataclass(slots=True)
class GraphDependencies:
    stt: STTPort
    tts: TTSPort
    endpointing: EndpointingPort
    kb_retrieve: KBRetrieveFn
    intent_classify: IntentClassifyFn
    report: ReportFn
    route: RouteFn
