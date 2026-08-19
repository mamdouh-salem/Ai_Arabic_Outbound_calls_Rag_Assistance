"""OpenAI Whisper-family STT adapter (Arabic)."""

from __future__ import annotations

import time

from openai import APIError, APITimeoutError, AsyncOpenAI, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from outbound_ai.common.arabic import normalize_arabic, normalize_light
from outbound_ai.config.settings import Settings, get_settings
from outbound_ai.voice.audio_utils import chunk_to_wav_bytes
from outbound_ai.voice.base import (
    AudioChunk,
    STTError,
    STTPort,
    TranscriptionResult,
    VoiceConfigError,
)

# Always prepended to the decoding prompt. Written in Egyptian colloquial so Whisper
# biases toward the register the customer will actually answer in.
_BASE_HINT = "مكالمة خدمة عملاء بالعامية المصرية عن متابعة شكوى أو تذكرة."

_TRANSIENT = (APITimeoutError, RateLimitError, APIError)


class WhisperSTT(STTPort):
    """Transcribes one customer turn per call.

    Stateless on purpose: retry counters and turn history live in the graph's CallState,
    not here, so the same instance is safe to share across concurrent calls.
    """

    def __init__(self, settings: Settings | None = None, client: AsyncOpenAI | None = None):
        self.settings = settings or get_settings()
        if client is None:
            if self.settings.openai_api_key is None:
                raise VoiceConfigError("OPENAI_API_KEY is not set — cannot start Whisper STT")
            client = AsyncOpenAI(api_key=self.settings.openai_api_key.get_secret_value())
        self._client = client

    async def transcribe(
        self,
        audio: AudioChunk,
        *,
        vocabulary_hints: list[str] | None = None,
    ) -> TranscriptionResult:
        # An accidental tap on the push-to-talk button is not a turn. Returning an empty
        # result (rather than raising) lets the graph reprompt without burning a retry.
        if audio.duration_ms < self.settings.stt_min_audio_ms or audio.is_silent:
            return TranscriptionResult(
                text_raw="",
                text_norm="",
                duration_ms=audio.duration_ms,
                model=self.settings.stt_model,
            )

        started = time.perf_counter()
        prompt = self._build_prompt(vocabulary_hints)
        raw_text = await self._call_api(chunk_to_wav_bytes(audio), prompt)
        latency_ms = int((time.perf_counter() - started) * 1000)

        return TranscriptionResult(
            # Light normalization only: strips tashkeel and stray whitespace but keeps
            # letter forms, so the transcript still reads as correct Arabic for QA.
            text_raw=normalize_light(raw_text),
            text_norm=normalize_arabic(raw_text),
            language=self.settings.stt_language,
            duration_ms=audio.duration_ms,
            model=self.settings.stt_model,
            latency_ms=latency_ms,
        )

    def _build_prompt(self, vocabulary_hints: list[str] | None) -> str:
        """Bias decoding toward this call's vocabulary.

        Mixed Arabic/English product names and ticket ids are exactly what Whisper
        transliterates inconsistently. Feeding them in makes the downstream intent
        classifier see a stable string instead of a new spelling every call.
        """
        if not vocabulary_hints:
            return _BASE_HINT
        terms = ", ".join(dict.fromkeys(h.strip() for h in vocabulary_hints if h and h.strip()))
        return f"{_BASE_HINT} مصطلحات متوقعة: {terms}." if terms else _BASE_HINT

    @retry(
        retry=retry_if_exception_type(_TRANSIENT),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        reraise=True,
    )
    async def _call_api(self, wav_bytes: bytes, prompt: str) -> str:
        try:
            response = await self._client.audio.transcriptions.create(
                file=("turn.wav", wav_bytes, "audio/wav"),
                model=self.settings.stt_model,
                language=self.settings.stt_language,
                prompt=prompt,
                temperature=0.0,
                response_format="json",
            )
        except _TRANSIENT:
            raise
        except Exception as exc:  # noqa: BLE001 - adapter boundary: one error type upstream
            raise STTError(f"transcription failed: {exc}") from exc
        return (getattr(response, "text", "") or "").strip()
