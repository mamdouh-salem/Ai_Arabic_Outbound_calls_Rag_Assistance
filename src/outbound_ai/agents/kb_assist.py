"""Adapter between the RAG pipeline (rag/generation.py) and the graph's
KBRetrieveFn contract (graph/deps.py) — the graph doesn't know anything
about hybrid search, local models, or grounding; it just gets back
(answer_text, retrieved_chunks, kb_answer_given).
"""
from __future__ import annotations

import asyncio

from outbound_ai.rag.generation import generate_answer


async def retrieve(query_text: str, kb_category: str) -> tuple[str, list[dict], bool]:
    """Blocking (GPU-bound via generate_answer), so offloaded to a thread —
    same reasoning as agents/intent_classifier.py.
    """
    result = await asyncio.to_thread(generate_answer, query_text, kb_category)

    kb_answer_given = result["chunks_used"] > 0
    retrieved_chunks = [{"source": s} for s in result["sources"]]

    return result["answer"], retrieved_chunks, kb_answer_given
