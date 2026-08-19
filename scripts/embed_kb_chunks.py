"""
Backfill embeddings for knowledge_base_chunks rows using a local
sentence-transformers model (no external API calls, no cost).

Run from the project root:
    python scripts/embed_kb_chunks.py
    python scripts/embed_kb_chunks.py --batch-size 50 --dry-run
"""
from __future__ import annotations

import argparse
import sys

import psycopg
import structlog
from pgvector.psycopg import register_vector
from sentence_transformers import SentenceTransformer

from outbound_ai.config.settings import get_settings

log = structlog.get_logger(__name__)

SELECT_SQL = """
    SELECT id, content
    FROM knowledge_base_chunks
    WHERE embedding IS NULL
    ORDER BY created_at
    LIMIT %(limit)s
"""

UPDATE_SQL = """
    UPDATE knowledge_base_chunks
    SET embedding = %(embedding)s
    WHERE id = %(id)s
"""


def run(batch_size: int, dry_run: bool) -> int:
    settings = get_settings()

    if not settings.database_url:
        log.error("missing_database_url")
        return 1

    model_name = settings.local_embedding_model
    expected_dim = settings.local_embedding_dim

    log.info("loading_model", model=model_name)
    model = SentenceTransformer(model_name)

    total_embedded = 0

    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        register_vector(conn)

        while True:
            with conn.cursor() as cur:
                cur.execute(SELECT_SQL, {"limit": batch_size})
                rows = cur.fetchall()

            if not rows:
                break

            ids = [row[0] for row in rows]
            texts = [row[1] for row in rows]

            log.info("embedding_batch", count=len(texts), model=model_name)
            embeddings = model.encode(texts, show_progress_bar=False).tolist()

            for embedding in embeddings:
                if len(embedding) != expected_dim:
                    log.error(
                        "embedding_dim_mismatch",
                        expected=expected_dim,
                        got=len(embedding),
                    )
                    return 1

            if dry_run:
                log.info("dry_run_skip_write", count=len(ids))
                total_embedded += len(ids)
                # Dry run only previews one batch so it doesn't loop forever
                # over rows it never actually clears.
                break

            with conn.cursor() as cur:
                for row_id, embedding in zip(ids, embeddings, strict=True):
                    cur.execute(UPDATE_SQL, {"id": row_id, "embedding": embedding})
            conn.commit()

            total_embedded += len(ids)
            log.info("batch_committed", total_embedded=total_embedded)

    log.info("done", total_embedded=total_embedded)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Rows per encode() call / DB round trip (default: 100)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Embed one batch and log it, but don't write to the DB",
    )
    args = parser.parse_args()

    sys.exit(run(batch_size=args.batch_size, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
