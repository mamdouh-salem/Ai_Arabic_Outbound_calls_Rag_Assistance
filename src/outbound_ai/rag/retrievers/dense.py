"""Dense (semantic) retrieval over knowledge_base_chunks using pgvector.

Cosine distance via the `<=>` operator (requires the hnsw vector_cosine_ops
index already present on the embedding column — see the table's DDL).
"""
from __future__ import annotations
from pgvector import Vector
from dataclasses import dataclass

import psycopg
from pgvector.psycopg import register_vector

from outbound_ai.config.settings import get_settings
from outbound_ai.rag.embeddings import embed_query


@dataclass
class RetrievedChunk:
    id: str
    content: str
    metadata: dict
    score: float
    source: str  # which retriever found it — set by the hybrid fuser


# category is matched against metadata->>'category'; None = no filter.
# workspace_ids: tenant guard (list) — None = no filter (single-tenant/dev only).
DENSE_SQL = """
    SELECT id, content, metadata, 1 - (embedding <=> %(query_embedding)s) AS score
    FROM knowledge_base_chunks
    WHERE embedding IS NOT NULL
      AND (%(category)s::text IS NULL OR metadata ->> 'category' = %(category)s)
      AND (%(workspace_ids)s::uuid[] IS NULL
           OR workspace_id = ANY(%(workspace_ids)s::uuid[]))
    ORDER BY embedding <=> %(query_embedding)s
    LIMIT %(top_k)s
"""


def dense_search(
    query: str,
    top_k: int | None = None,
    category: str | None = None,
    workspace_ids: list[str] | None = None,
) -> list[RetrievedChunk]:
    settings = get_settings()
    top_k = top_k or settings.rag_top_k_dense

    query_embedding = Vector(embed_query(query))

    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            cur.execute(
                DENSE_SQL,
                {
                    "query_embedding": query_embedding,
                    "category": category,
                    "workspace_ids": workspace_ids,
                    "top_k": top_k,
                },
            )
            rows = cur.fetchall()

    return [
        RetrievedChunk(id=str(row[0]), content=row[1], metadata=row[2], score=row[3], source="dense")
        for row in rows
    ]
