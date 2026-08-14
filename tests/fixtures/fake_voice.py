"""In-memory STT/TTS doubles.

These let the whole call graph be exercised with zero API calls and zero cost, which is
what makes it practical to test the branching logic (resolved / unresolved / unclear /
wants_human) on every run.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import numpy as np

from outbound_ai.common.arabic import normalize_arabic, normalize_light
from outbound_ai.voice.base import (
    SAMPLE_RATE,
    AudioChunk,
    STTPort,
    TranscriptionResult,
    TTSPort,
)
from outbound_ai.voice.text_stream import sentence_chunker


def silence(duration_ms: int = 1000, sample_rate: int = SAMPLE_RATE) -> AudioChunk:
    return AudioChunk(
        pcm=np.zeros(int(sample_rate * duration_ms / 1000), dtype=np.int16),
        sample_rate=sample_rate,
    )


def tone(
    duration_ms: int = 1000,
    freq_hz: float = 220.0,
    sample_rate: int = SAMPLE_RATE,
) -> AudioChunk:
    """Non-silent audio, so `is_silent` and duration guards behave realistically."""
    t = np.arange(int(sample_rate * duration_ms / 1000)) / sample_rate
    pcm = (np.sin(2 * np.pi * freq_hz * t) * 8000).astype(np.int16)
    return AudioChunk(pcm=pcm, sample_rate=sample_rate)


class FakeSTT(STTPort):
    """Returns a scripted transcript per turn, ignoring the audio entirely."""

    def __init__(self, script: list[str] | None = None) -> None:
        self.script = list(script or [])
        self.calls: list[tuple[int, list[str]]] = []

    async def transcribe(
        self,
        audio: AudioChunk,
        *,
        vocabulary_hints: list[str] | None = None,
    ) -> TranscriptionResult:
        self.calls.append((audio.duration_ms, list(vocabulary_hints or [])))
        text = self.script.pop(0) if self.script else ""
        return TranscriptionResult(
            text_raw=normalize_light(text),
            text_norm=normalize_arabic(text),
            duration_ms=audio.duration_ms,
            model="fake-stt",
        )


class FakeTTS(TTSPort):
    """Records what was spoken and returns silence of a plausible length.

    Duration is derived from character count so latency-shaped assertions stay meaningful
    without any network call.
    """

    MS_PER_CHAR = 60

    def __init__(self) -> None:
        self.spoken: list[str] = []

    async def synthesize(self, text: str, *, high_quality: bool = False) -> AudioChunk:
        self.spoken.append(text)
        return silence(max(len(text) * self.MS_PER_CHAR, 100))

    async def stream(self, text_stream: AsyncIterator[str]) -> AsyncIterator[AudioChunk]:
        async for segment in sentence_chunker(text_stream):
            yield await self.synthesize(segment)
