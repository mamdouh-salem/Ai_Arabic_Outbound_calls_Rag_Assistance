"""
Assembles and compiles the LangGraph workflow.

build_graph now takes a GraphDependencies instance instead of constructing
adapters itself — the caller (api/app.py, scripts, tests) decides whether
that's real Whisper/ElevenLabs/Vonage adapters or fakes.

Checkpointer note: still MemorySaver (in-process, lost on restart). Swapping
to PostgresSaver needs a long-lived connection managed through FastAPI's
lifespan — kept separate so it doesn't block getting the real voice/RAG
wiring proven out first.
"""
from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from outbound_ai.graph import edges, nodes
from outbound_ai.graph.deps import GraphDependencies
from outbound_ai.graph.state import GraphState


def build_graph(deps: GraphDependencies, checkpointer=None):
    if checkpointer is None:
        checkpointer = MemorySaver()

    g = StateGraph(GraphState)

    g.add_node("outbound_call", nodes.make_outbound_call_node(deps))
    g.add_node("intent_classifier", nodes.make_intent_classifier_node(deps))
    g.add_node("kb_assist", nodes.make_kb_assist_node(deps))
    g.add_node("routing", nodes.make_routing_node(deps))
    g.add_node("reporting", nodes.make_reporting_node(deps))

    g.set_entry_point("outbound_call")
    g.add_edge("outbound_call", "intent_classifier")

    g.add_conditional_edges(
        "intent_classifier",
        edges.route_on_intent,
        {
            "resolved": "reporting",
            "unresolved": "kb_assist",
            "wants_human": "routing",
        },
    )
    g.add_conditional_edges(
        "kb_assist",
        edges.route_after_kb,
        {
            "resolved": "reporting",
            "handoff": "routing",
        },
    )
    g.add_edge("routing", "reporting")
    g.add_edge("reporting", END)

    return g.compile(checkpointer=checkpointer)
