"""Local grounded generation via the shared Qwen2.5-7B-Instruct model.

Model loading now lives in common/local_llm.py, shared with
agents/intent_classifier.py — see that module's docstring for why.
"""
from __future__ import annotations

import structlog

from outbound_ai.common.local_llm import run_chat
from outbound_ai.config.settings import get_settings
from outbound_ai.prompts.rag_prompt import (
    NO_CONTEXT_FALLBACK,
    TROUBLESHOOT_NO_CONTEXT_FALLBACK,
    build_messages,
    build_troubleshooting_messages,
)
from outbound_ai.rag.context_builder import build_context, sources_used
from outbound_ai.rag.retrievers.hybrid import hybrid_search

log = structlog.get_logger(__name__)


def generate_answer(
    question: str,
    category: str | None = None,
    workspace_id: str | None = None,
    style: str = "qa",
    ticket_context: str = "",
) -> dict:
    """Run the full RAG loop: retrieve -> build context -> generate.

    style="qa"   — knowledge-base chat answers (MSA, citation markers)
    style="call" — live-call troubleshooting coach (Egyptian dialect, one
                   actionable step, ends with "لما تخلص قولّي خلصت")

    Returns {"answer", "sources", "chunks_used", "citations"} where citations
    carry per-chunk provenance (id, source, score, snippet) for UI rendering.
    """
    settings = get_settings()
    chunks = hybrid_search(question, category=category, workspace_id=workspace_id)
    fallback = TROUBLESHOOT_NO_CONTEXT_FALLBACK if style == "call" else NO_CONTEXT_FALLBACK
    if not chunks:
        return {
            "answer": fallback,
            "sources": [],
            "chunks_used": 0,
            "citations": [],
        }

    context = build_context(chunks)
    if style == "call":
        messages = build_troubleshooting_messages(
            question, context, ticket_context=ticket_context
        )
    else:
        messages = build_messages(question=question, context=context)

    answer = run_chat(
        messages,
        max_new_tokens=settings.generation_max_new_tokens,
        temperature=settings.generation_temperature,
    )

    citations = [
        {
            # [1]-style index matching the bracketed markers the prompt asks
            # the model to emit inside the answer text
            "index": i,
            "id": c.id,
            "source": c.metadata.get("source", "unknown"),
            "score": round(c.rrf_score, 4),
            "snippet": c.content[:180],
        }
        for i, c in enumerate(chunks, start=1)
    ]
    return {
        "answer": answer,
        "sources": sources_used(chunks),
        "chunks_used": len(chunks),
        "citations": citations,
    }
