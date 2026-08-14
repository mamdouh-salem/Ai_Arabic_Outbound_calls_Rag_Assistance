"""Buffering an LLM token stream into TTS-sized segments.

Pure text, no I/O and no API keys — unit-testable on its own.

Why not send tokens straight to TTS: Arabic prosody is decided at clause level. Three-word
fragments come back flat and seam-y, and every request pays fixed API overhead. Flushing on
punctuation (or at a length ceiling) keeps each request long enough to sound natural while
still starting playback long before the LLM has finished generating.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable

# Arabic and ASCII sentence terminators. `،` and `؛` are included because Arabic clauses
# are long: waiting for a full stop can mean waiting for the entire turn.
SENTENCE_ENDINGS = frozenset(".!?؟،؛:\n")

# Below this, a flush is likely to be a fragment like "نعم،" — hold it and keep buffering.
MIN_SEGMENT_CHARS = 25
# Above this, flush regardless of punctuation so playback is not held hostage by a
# run-on sentence.
MAX_SEGMENT_CHARS = 180


def split_segments(text: str) -> list[str]:
    """Split a complete string the same way the streaming chunker would."""
    segments: list[str] = []
    buffer = ""
    for char in text:
        buffer += char
        if _should_flush(buffer, char):
            segments.append(buffer.strip())
            buffer = ""
    if buffer.strip():
        segments.append(buffer.strip())
    return [s for s in segments if s]


def _should_flush(buffer: str, last_char: str) -> bool:
    stripped = len(buffer.strip())
    if stripped >= MAX_SEGMENT_CHARS:
        return True
    return last_char in SENTENCE_ENDINGS and stripped >= MIN_SEGMENT_CHARS


async def sentence_chunker(token_stream: AsyncIterator[str]) -> AsyncIterator[str]:
    """Group an async token stream into sentence-sized segments.

    Yields as soon as a segment is complete, so the first segment reaches TTS while the
    model is still writing the rest of the turn.
    """
    buffer = ""
    async for token in token_stream:
        if not token:
            continue
        buffer += token
        while True:
            flush_at = _find_flush_point(buffer)
            if flush_at is None:
                break
            segment, buffer = buffer[:flush_at].strip(), buffer[flush_at:]
            if segment:
                yield segment
    if buffer.strip():
        yield buffer.strip()


def _find_flush_point(buffer: str) -> int | None:
    """Index to cut at, or None if the buffer is not ready to flush."""
    for index, char in enumerate(buffer):
        if _should_flush(buffer[: index + 1], char):
            return index + 1
    return None


async def as_async_stream(tokens: Iterable[str]) -> AsyncIterator[str]:
    """Adapt a plain iterable of tokens to an async stream. Used in tests and for
    replaying a fixed script through the streaming TTS path."""
    for token in tokens:
        yield token
