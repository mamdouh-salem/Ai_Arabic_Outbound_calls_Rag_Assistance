"""Sparse (keyword) retrieval over knowledge_base_chunks using Postgres FTS.

Uses the `fts_tokens` tsvector column, which is kept in sync automatically
by the `tsvectorupdate` trigger on insert/update (arabic text search config).
"""
from __future__ import annotations

import psycopg

from outbound_ai.config.settings import get_settings
from outbound_ai.rag.retrievers.dense import RetrievedChunk

SPARSE_SQL = """
    SELECT id, content, metadata, ts_rank(fts_tokens, plainto_tsquery('arabic', %(query)s)) AS score
    FROM knowledge_base_chunks
    WHERE fts_tokens @@ plainto_tsquery('arabic', %(query)s)
      AND (%(category)s::text IS NULL OR metadata ->> 'category' = %(category)s)
      AND (%(workspace_ids)s::uuid[] IS NULL
           OR workspace_id = ANY(%(workspace_ids)s::uuid[]))
    ORDER BY score DESC
    LIMIT %(top_k)s
"""


def sparse_search(
    query: str,
    top_k: int | None = None,
    category: str | None = None,
    workspace_ids: list[str] | None = None,
) -> list[RetrievedChunk]:
    settings = get_settings()
    top_k = top_k or settings.rag_top_k_sparse

    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                SPARSE_SQL,
                {
                    "query": query,
                    "category": category,
                    "workspace_ids": workspace_ids,
                    "top_k": top_k,
                },
            )
            rows = cur.fetchall()

    return [
        RetrievedChunk(id=str(row[0]), content=row[1], metadata=row[2], score=row[3], source="sparse")
        for row in rows
    ]
