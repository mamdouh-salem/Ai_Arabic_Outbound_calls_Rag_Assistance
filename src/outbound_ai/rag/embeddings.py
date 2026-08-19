"""Single shared SentenceTransformer instance for query-time embedding.

The backfill script (scripts/embed_kb_chunks.py) embeds KB rows offline.
This module embeds *queries* at request time, using the same model so
query and document vectors live in the same space.
"""
from __future__ import annotations

from functools import lru_cache

from sentence_transformers import SentenceTransformer

from outbound_ai.config.settings import get_settings


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    """Cached singleton — loading the model is the slow part, do it once."""
    settings = get_settings()
    return SentenceTransformer(settings.local_embedding_model)


def embed_query(text: str) -> list[float]:
    """Embed a single query string. Returns a plain list (pgvector-ready)."""
    model = get_embedding_model()
    return model.encode(text, show_progress_bar=False).tolist()
