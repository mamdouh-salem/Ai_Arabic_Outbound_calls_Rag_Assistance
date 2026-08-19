"""Local grounded generation via the shared Qwen2.5-7B-Instruct model.

Model loading now lives in common/local_llm.py, shared with
agents/intent_classifier.py — see that module's docstring for why.
"""
from __future__ import annotations

import structlog

from outbound_ai.common.local_llm import run_chat
from outbound_ai.config.settings import get_settings
from outbound_ai.prompts.rag_prompt import NO_CONTEXT_FALLBACK, build_messages
from outbound_ai.rag.context_builder import build_context, sources_used
from outbound_ai.rag.retrievers.hybrid import hybrid_search

log = structlog.get_logger(__name__)


def generate_answer(question: str, category: str | None = None) -> dict:
    """Run the full RAG loop: retrieve -> build context -> generate.

    Returns {"answer": str, "sources": list[str], "chunks_used": int}.
    """
    settings = get_settings()
    chunks = hybrid_search(question, category=category)
    if not chunks:
        return {"answer": NO_CONTEXT_FALLBACK, "sources": [], "chunks_used": 0}

    context = build_context(chunks)
    messages = build_messages(question=question, context=context)

    answer = run_chat(
        messages,
        max_new_tokens=settings.generation_max_new_tokens,
        temperature=settings.generation_temperature,
    )

    return {
        "answer": answer,
        "sources": sources_used(chunks),
        "chunks_used": len(chunks),
    }
