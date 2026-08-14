"""ElevenLabs TTS adapter (streaming, Arabic)."""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from pathlib import Path

from elevenlabs.client import AsyncElevenLabs
from tenacity import retry, stop_after_attempt, wait_exponential

from outbound_ai.common.arabic import normalize_light
from outbound_ai.config.settings import Settings, get_settings
from outbound_ai.voice.audio_utils import PCMStreamAssembler, concat, read_wav, write_wav
from outbound_ai.voice.base import (
    SAMPLE_RATE,
    AudioChunk,
    TTSError,
    TTSPort,
    VoiceConfigError,
)
from outbound_ai.voice.text_stream import sentence_chunker


def _sample_rate_from_format(output_format: str) -> int:
    """`pcm_16000` -> 16000. Falls back to the canonical rate for non-PCM formats."""
    parts = output_format.split("_")
    if parts and parts[-1].isdigit():
        return int(parts[-1])
    return SAMPLE_RATE


class ElevenLabsTTS(TTSPort):
    """Streaming Arabic speech synthesis.

    Two models are configured: a fast one for live call turns and a higher-quality one for
    static prompts rendered once and cached. Latency matters far more mid-turn than it
    does for a greeting we render ahead of time.
    """

    def __init__(self, settings: Settings | None = None, client: AsyncElevenLabs | None = None):
        self.settings = settings or get_settings()
        if not self.settings.elevenlabs_voice_id:
            raise VoiceConfigError("ELEVENLABS_VOICE_ID is not set — pick a voice first")
        if client is None:
            if self.settings.elevenlabs_api_key is None:
                raise VoiceConfigError("ELEVENLABS_API_KEY is not set — cannot start TTS")
            client = AsyncElevenLabs(api_key=self.settings.elevenlabs_api_key.get_secret_value())
        self._client = client
        self._sample_rate = _sample_rate_from_format(self.settings.elevenlabs_output_format)

    # ------------------------------------------------------------------ port methods

    async def synthesize(self, text: str, *, high_quality: bool = False) -> AudioChunk:
        chunks = [chunk async for chunk in self._synthesize_stream(text, high_quality=high_quality)]
        if not chunks:
            raise TTSError(f"no audio returned for: {text[:60]!r}")
        return concat(chunks)

    async def stream(self, text_stream: AsyncIterator[str]) -> AsyncIterator[AudioChunk]:
        """Render an LLM token stream to audio, segment by segment.

        The first segment reaches the speaker while the model is still generating the
        rest of the turn — this is the whole reason perceived latency stays under ~3 s.
        """
        async for segment in sentence_chunker(text_stream):
            async for chunk in self._synthesize_stream(segment):
                yield chunk

    # ------------------------------------------------------------------ static cache

    async def synthesize_cached(self, text: str) -> AudioChunk:
        """Render once, reuse forever.

        The greeting, the reprompt line, the handoff line and the closing line are fixed
        text. Caching them makes the most latency-visible moment of the call — the
        opening greeting — cost 0 ms of synthesis.
        """
        path = self._cache_path(text)
        if path.exists():
            return read_wav(path)
        chunk = await self.synthesize(text, high_quality=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_wav(path, chunk)
        return chunk

    def _cache_path(self, text: str) -> Path:
        key = "|".join(
            [
                normalize_light(text),
                self.settings.elevenlabs_voice_id,
                self.settings.elevenlabs_quality_model_id,
                str(self._sample_rate),
            ]
        )
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
        return self.settings.audio_cache_path / f"{digest}.wav"

    # ----------------------------------------------------------------------- internals

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=4))
    async def _synthesize_stream(
        self, text: str, *, high_quality: bool = False
    ) -> AsyncIterator[AudioChunk]:
        text = normalize_light(text)
        if not text:
            return

        model_id = (
            self.settings.elevenlabs_quality_model_id
            if high_quality
            else self.settings.elevenlabs_model_id
        )
        assembler = PCMStreamAssembler(self._sample_rate)
        try:
            response = self._client.text_to_speech.convert(
                voice_id=self.settings.elevenlabs_voice_id,
                text=text,
                model_id=model_id,
                output_format=self.settings.elevenlabs_output_format,
            )
            async for raw in _iter_bytes(response):
                chunk = assembler.push(raw)
                if chunk is not None and len(chunk.pcm):
                    yield chunk
        except Exception as exc:  # noqa: BLE001 - adapter boundary: one error type upstream
            raise TTSError(f"synthesis failed for {text[:60]!r}: {exc}") from exc

        tail = assembler.flush()
        if tail is not None and len(tail.pcm):
            yield tail


async def _iter_bytes(response) -> AsyncIterator[bytes]:
    """Normalize the SDK's return shape.

    Depending on the elevenlabs version, `convert` returns an async iterator of byte
    chunks, a coroutine resolving to one, or a single bytes blob. Handling all three here
    keeps the version pin loose.
    """
    if hasattr(response, "__aiter__"):
        async for chunk in response:
            if chunk:
                yield chunk
        return

    resolved = await response if hasattr(response, "__await__") else response
    if isinstance(resolved, (bytes, bytearray)):
        yield bytes(resolved)
        return
    if hasattr(resolved, "__aiter__"):
        async for chunk in resolved:
            if chunk:
                yield chunk
        return
    for chunk in resolved:
        if chunk:
            yield chunk
