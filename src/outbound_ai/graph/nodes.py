"""
Graph node factories. Each factory closes over GraphDependencies and returns
an async node function — no node constructs its own adapters, so a test can
inject fakes without touching this file.

STUB NOTICE: intent_classifier, routing, and reporting still return canned
data — the corresponding agents/ modules don't exist yet. outbound_call and
kb_assist are wired for real: outbound_call actually calls through
STTPort/TTSPort/EndpointingPort, and kb_assist calls deps.kb_retrieve (a
placeholder callable until agents/kb_assist.py + rag/pipeline.py exist —
see graph/deps.py).
"""
from __future__ import annotations

from outbound_ai.graph.deps import GraphDependencies
from outbound_ai.graph.state import GraphState


def make_outbound_call_node(deps: GraphDependencies):
    async def outbound_call_node(state: GraphState) -> dict:
        greeting = f"مرحبًا، معك المساعد الآلي بخصوص التذكرة رقم {state['ticket_id']}."
        await deps.tts.synthesize(greeting)

        customer_audio = await deps.endpointing.wait_for_end_of_speech()
        deps.endpointing.reset()

        transcription = await deps.stt.transcribe(customer_audio)

        return {
            "transcript": [
                {"role": "assistant", "content": greeting},
                {"role": "human", "content": transcription.text_raw},
            ],
        }

    return outbound_call_node


def make_intent_classifier_node(deps: GraphDependencies):
    async def intent_classifier_node(state: GraphState) -> dict:
        intent = await deps.intent_classify(state["transcript"])
        return {"intent": intent}

    return intent_classifier_node


def make_kb_assist_node(deps: GraphDependencies):
    async def kb_assist_node(state: GraphState) -> dict:
        last_customer_turn = next(
            (m.content for m in reversed(state["transcript"]) if m.type == "human"),
            "",
        )
        answer_text, chunks, resolved = await deps.kb_retrieve(
            last_customer_turn, state["kb_category"]
        )
        await deps.tts.synthesize(answer_text)
        return {
            "retrieved_chunks": chunks,
            "kb_answer_given": resolved,
            "transcript": [{"role": "assistant", "content": answer_text}],
        }

    return kb_assist_node


def make_routing_node(deps: GraphDependencies):
    async def routing_node(state: GraphState) -> dict:
        return await deps.route(state)

    return routing_node


def make_reporting_node(deps: GraphDependencies):
    async def reporting_node(state: GraphState) -> dict:
        return await deps.report(state)

    return reporting_node
