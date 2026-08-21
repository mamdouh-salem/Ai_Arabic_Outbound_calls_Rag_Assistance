"""KB document ingestion: text -> chunks -> embeddings -> knowledge_base_chunks.

Reuses the same local embedding model as query time (rag/embeddings.py) so
uploaded documents land in the same vector space. Every row is tagged with
workspace_id + category metadata, matching the workspace-aware match_chunks()
in migration 003 and the workspace-scoped retrievers.

Supported inputs: plain text / markdown / PDF (pypdf, optional import).
"""
from __future__ import annotations

import structlog
from pgvector.psycopg import register_vector
from psycopg import connect

from outbound_ai.config.settings import get_settings
from outbound_ai.rag.embeddings import get_embedding_model

log = structlog.get_logger(__name__)

# Chunk sizing: big enough to keep an SOP step in context, small enough that
# 5 retrieved chunks stay under the generation prompt budget.
CHUNK_MAX_CHARS = 1200
CHUNK_OVERLAP = 150


def extract_text_from_pdf(data: bytes) -> str:
    """Best-effort PDF text extraction via pypdf (declared optional extra)."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "PDF upload requires the 'pypdf' package (pip install pypdf)."
        ) from exc
    import io

    reader = PdfReader(io.BytesIO(data))
    return "\n\n".join((page.extract_text() or "") for page in reader.pages)


def chunk_text(
    text: str,
    max_chars: int = CHUNK_MAX_CHARS,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """Deterministic paragraph-aware chunker with tail overlap.

    Splits on blank lines first; paragraphs longer than max_chars are
    hard-split. Each chunk carries `overlap` chars from the previous one so
    sentences cut at a boundary remain retrievable by both halves.
    """
    text = text.strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    # Explode oversized paragraphs into hard slices.
    pieces: list[str] = []
    for para in paragraphs:
        if len(para) <= max_chars:
            pieces.append(para)
            continue
        for i in range(0, len(para), max_chars - overlap):
            piece = para[i : i + max_chars]
            pieces.append(piece)
            if i + max_chars >= len(para):
                break

    # Accumulate pieces into chunks under the cap, carrying overlap.
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        candidate = f"{current}\n\n{piece}" if current else piece
        if not current:
            current = candidate
            continue
        if len(candidate) <= max_chars:
            current = candidate
            continue
        chunks.append(current)
        tail = current[-overlap:]
        current = f"{tail}\n\n{piece}"
        if len(current) > max_chars:
            # Overlap would blow the budget on a near-cap single piece —
            # keep the invariant (every chunk <= max_chars) over overlap.
            current = piece
    if current:
        chunks.append(current)

    return chunks


INSERT_SQL = """
    insert into knowledge_base_chunks
        (content, metadata, workspace_id, embedding)
    values (%(content)s, %(metadata)s::jsonb, %(workspace_id)s::uuid, %(embedding)s)
"""


def ingest_document(
    content: str,
    *,
    source_name: str,
    category: str,
    workspace_id: str,
) -> dict:
    """Chunk + embed + insert one document. Returns a summary dict.

    Blocking (model.encode + DB round trip) — callers offload to a thread.
    """
    settings = get_settings()
    chunks = chunk_text(content)
    if not chunks:
        return {"source": source_name, "chunks": 0}

    model = get_embedding_model()
    embeddings = model.encode(chunks, show_progress_bar=False).tolist()

    inserted = 0
    with connect(settings.database_url.get_secret_value()) as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            for chunk, embedding in zip(chunks, embeddings, strict=True):
                cur.execute(
                    INSERT_SQL,
                    {
                        "content": chunk,
                        "metadata": '{"source": "%s", "category": "%s"}'
                        % (source_name.replace('"', ""), category),
                        "workspace_id": workspace_id,
                        "embedding": embedding,
                    },
                )
                inserted += 1
        conn.commit()

    log.info("kb_document_ingested", source=source_name, chunks=inserted, workspace=workspace_id)
    return {"source": source_name, "chunks": inserted}
