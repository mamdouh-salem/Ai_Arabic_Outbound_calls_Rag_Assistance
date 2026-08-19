"""
Runs the compiled graph once end-to-end using fake voice ports (no real
Whisper/ElevenLabs calls, no audio hardware) and a stub KB-retrieval
function, so you can confirm the graph + voice-port wiring works before real
adapters or the RAG pipeline are plugged in.

If you already have real fakes elsewhere (your README's "Done" section
mentions the voice layer ships with fakes for the 35 unit tests) — prefer
those over the ones defined here to avoid two slightly different fake
implementations drifting apart. These are self-contained here only so this
script has zero dependency on where those live.

Run from the repo root:
    python scripts/smoke_test_graph.py
"""
from __future__ import annotations

import asyncio

import numpy as np

from outbound_ai.config.settings import get_settings  # noqa: F401  (loads .env + exports tracing env vars)
from outbound_ai.graph.build import build_graph
from outbound_ai.graph.deps import GraphDependencies
from outbound_ai.voice.base import (
    AudioChunk,
    EndpointingPort,
    STTPort,
    TranscriptionResult,
    TTSPort,
)
from langchain_core.tracers.langchain import wait_for_all_tracers


class FakeSTT(STTPort):
    async def transcribe(self, audio, *, vocabulary_hints=None):
        return TranscriptionResult(
            text_raw="الراوتر بتاعي بيفصل باستمرار",
            text_norm="الراوتر بتاعي بيفصل باستمرار",
            model="fake-stt",
        )


class FakeTTS(TTSPort):
    async def synthesize(self, text, *, high_quality=False):
        return AudioChunk(pcm=np.zeros(1600, dtype=np.int16))

    async def stream(self, text_stream):
        async for _ in text_stream:
            yield AudioChunk(pcm=np.zeros(1600, dtype=np.int16))


class FakeEndpointing(EndpointingPort):
    async def wait_for_end_of_speech(self, timeout_s=None):
        return AudioChunk(pcm=np.zeros(1600, dtype=np.int16))

    def reset(self):
        pass


async def fake_kb_retrieve(query_text: str, kb_category: str):
    # TODO: replace with the real rag pipeline call once agents/kb_assist.py exists
    return (
        "(stub) هذا رد تجريبي بدلاً من الاسترجاع الفعلي من قاعدة المعرفة.",
        [{"id": "stub-chunk-1", "content": "stub", "source": "stub", "score": 0.0}],
        False,
    )


async def fake_intent_classify(transcript: list) -> str:
    return "unresolved"


async def fake_report(state: dict) -> dict:
    outcome = "escalated" if state.get("escalated") else "unresolved"
    return {"call_outcome": outcome, "call_summary": "(stub) ملخص تجريبي للمكالمة."}


async def fake_route(state: dict) -> dict:
    return {
        "escalated": True,
        "escalation_reason": "kb_could_not_resolve",
        "escalation_priority": "medium",
        "escalation_brief": "(stub) موجز تجريبي لتحويل المكالمة.",
    }


async def main():
    deps = GraphDependencies(
        stt=FakeSTT(),
        tts=FakeTTS(),
        endpointing=FakeEndpointing(),
        kb_retrieve=fake_kb_retrieve,
        intent_classify=fake_intent_classify,
        report=fake_report,
        route=fake_route,
    )
    app = build_graph(deps)

    result = await app.ainvoke(
        {
            "ticket_id": "test-ticket-001",
            "customer_id": "test-customer-001",
            "customer_phone": "+201000000000",
            "kb_category": "routers",
            "transcript": [],
            "intent": None,
            "retrieved_chunks": [],
            "kb_answer_given": False,
            "escalated": False,
            "escalation_reason": None,
            "escalation_priority": None,
            "escalation_brief": None,
            "call_outcome": None,
            "call_summary": None,
        },
        config={"configurable": {"thread_id": "smoke-test-1"}},
    )

    print("\n--- Final state ---")
    for key, value in result.items():
        print(f"{key}: {value}")

    # Short scripts can exit before LangSmith's background batching thread
    # submits pending traces — force a flush so the run actually shows up.
    print("\nFlushing pending LangSmith traces...")
    wait_for_all_tracers()
    print("Done — check smith.langchain.com now.")


if __name__ == "__main__":
    asyncio.run(main())
