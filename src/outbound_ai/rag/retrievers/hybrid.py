"""Hybrid retrieval: dense (pgvector) + sparse (Postgres FTS) fused with RRF.

Reciprocal Rank Fusion (RRF) combines two ranked lists without needing their
raw scores to be on the same scale (cosine similarity vs ts_rank aren't
comparable directly) — each document's fused score is the sum, across the
lists it appears in, of 1 / (k + rank).

Metadata filtering (e.g. category='billing') is pushed down into both SQL
queries rather than applied after fusion, so it doesn't waste top_k slots
on chunks that would be filtered out anyway.
"""
from __future__ import annotations

from dataclasses import dataclass

from outbound_ai.config.settings import get_settings
from outbound_ai.rag.retrievers.dense import RetrievedChunk, dense_search
from outbound_ai.rag.retrievers.sparse import sparse_search


@dataclass
class FusedChunk:
    id: str
    content: str
    metadata: dict
    rrf_score: float
    found_by: list[str]  # ["dense"], ["sparse"], or both


def _rrf_fuse(
    ranked_lists: list[list[RetrievedChunk]],
    k: int,
) -> list[FusedChunk]:
    scores: dict[str, float] = {}
    chunks: dict[str, RetrievedChunk] = {}
    found_by: dict[str, set[str]] = {}

    for ranked_list in ranked_lists:
        for rank, chunk in enumerate(ranked_list, start=1):
            scores[chunk.id] = scores.get(chunk.id, 0.0) + 1.0 / (k + rank)
            chunks[chunk.id] = chunk
            found_by.setdefault(chunk.id, set()).add(chunk.source)

    fused = [
        FusedChunk(
            id=chunk_id,
            content=chunks[chunk_id].content,
            metadata=chunks[chunk_id].metadata,
            rrf_score=score,
            found_by=sorted(found_by[chunk_id]),
        )
        for chunk_id, score in scores.items()
    ]
    fused.sort(key=lambda c: c.rrf_score, reverse=True)
    return fused


def hybrid_search(
    query: str,
    category: str | None = None,
    top_n: int | None = None,
) -> list[FusedChunk]:
    """Run dense + sparse retrieval, fuse with RRF, return the top_n chunks.

    category: optional metadata filter, e.g. "billing" / "technical"
              (matches the kb_category values used on the tickets table).
    """
    settings = get_settings()
    top_n = top_n or settings.rag_top_n_after_rerank

    dense_results = dense_search(query, top_k=settings.rag_top_k_dense, category=category)
    sparse_results = sparse_search(query, top_k=settings.rag_top_k_sparse, category=category)

    fused = _rrf_fuse([dense_results, sparse_results], k=settings.rag_rrf_k)
    return fused[:top_n]
