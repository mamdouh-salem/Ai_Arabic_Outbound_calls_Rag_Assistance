"""Turns a list of FusedChunk into the context block the prompt template uses.

Each chunk is tagged with its metadata source file so the generation prompt
can (and must) cite it, and so we can trace an answer back to the SOP it
came from.
"""
from __future__ import annotations

from outbound_ai.rag.retrievers.hybrid import FusedChunk

# Keeps the prompt from ballooning if a query pulls in unusually long chunks.
MAX_CONTEXT_CHARS = 4000


def build_context(chunks: list[FusedChunk]) -> str:
    """Format chunks as numbered, source-tagged blocks. Empty list -> ''."""
    if not chunks:
        return ""

    blocks: list[str] = []
    running_length = 0

    for i, chunk in enumerate(chunks, start=1):
        source = chunk.metadata.get("source", "unknown")
        block = f"[{i}] (المصدر: {source})\n{chunk.content}"

        if running_length + len(block) > MAX_CONTEXT_CHARS and blocks:
            # Stop before overflowing the budget, but always keep at least
            # one block even if it alone exceeds MAX_CONTEXT_CHARS.
            break

        blocks.append(block)
        running_length += len(block)

    return "\n\n".join(blocks)


def sources_used(chunks: list[FusedChunk]) -> list[str]:
    """Distinct source filenames, in the order chunks were ranked."""
    seen: list[str] = []
    for chunk in chunks:
        source = chunk.metadata.get("source", "unknown")
        if source not in seen:
            seen.append(source)
    return seen
