"""
Runs the compiled graph with REAL intent classification and REAL RAG
retrieval/generation — actually loads and calls your local Qwen2.5-7B model
and hybrid_search against Supabase. Voice ports (STT/TTS/endpointing) stay
fake, since no telephony adapter exists yet — this test is about proving
the LLM + RAG chain works *through the graph*, not just in isolation via
test_rag_pipeline.py.

Expect this to be slow the first run: model load alone is ~10-20s per your
own local_llm.py docstring, then two more generate calls (intent
classification + RAG answer) on top of that. Not a bug if it takes a while.

Run from the repo root:
    python scripts/smoke_test_graph_real.py
"""
from __future__ import annotations

import asyncio

import numpy as np

from outbound_ai.agents import intent_classifier, kb_assist, reporting, routing
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
        # Deliberately a router complaint — matches kb_category="routers"
        # in the invoke() call below, so real hybrid_search has something
        # relevant to actually retrieve against.
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


async def main():
    deps = GraphDependencies(
        stt=FakeSTT(),
        tts=FakeTTS(),
        endpointing=FakeEndpointing(),
        kb_retrieve=kb_assist.retrieve,          # real
        intent_classify=intent_classifier.classify,  # real
        report=reporting.summarize,              # real
        route=routing.escalate,                  # real
    )
    app = build_graph(deps)

    print("Running graph with real intent classification + RAG (this loads the model — be patient)...")

    result = await app.ainvoke(
        {
            "ticket_id": "test-ticket-real-001",
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
        config={"configurable": {"thread_id": "smoke-test-real-1"}},
    )

    print("\n--- Final state ---")
    for key, value in result.items():
        print(f"{key}: {value}")

    print("\nFlushing pending LangSmith traces...")
    wait_for_all_tracers()
    print("Done — check smith.langchain.com now.")


if __name__ == "__main__":
    asyncio.run(main())
