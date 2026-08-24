"""Shared voice services used by BOTH the live-call flow and the RAG chat:
- transcribe_audio_bytes(): speech → Arabic text (Gemini)
- synthesize_to_cache():    Arabic text → WAV file in the audio cache,
                            served publicly at /audio/{name}
"""
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import structlog

from outbound_ai.config.settings import get_settings
from outbound_ai.voice.tts_elevenlabs import ElevenLabsTTS

log = structlog.get_logger(__name__)

_tts: ElevenLabsTTS | None = None


def get_tts() -> ElevenLabsTTS | None:
    global _tts
    if _tts is None:
        try:
            _tts = ElevenLabsTTS()
        except Exception as exc:
            log.warning("tts_unavailable", error=str(exc))
    return _tts


def transcribe_audio_bytes(data: bytes, mime: str = "audio/mpeg") -> str:
    """Arabic speech → text via Gemini. Blocking (network) — offload with
    asyncio.to_thread from async callers."""
    import google.generativeai as genai

    settings = get_settings()
    genai.configure(api_key=settings.gemini_api_key.get_secret_value())
    model = genai.GenerativeModel(settings.gemini_model)
    result = model.generate_content([
        "فرّغ التسجيل ده لنص عربي قصير. اكتب النص بس بدون أي شرح.",
        {"mime_type": mime, "data": data},
    ])
    return (result.text or "").strip()


async def synthesize_to_cache(text: str, *, prefix: str = "tts") -> Path | None:
    """ElevenLabs text → cached WAV path (or None if synthesis unavailable).
    Same cache dir the live-call flow uses, so /audio/{name} serves it."""
    tts = get_tts()
    if tts is None:
        return None
    try:
        import soundfile as sf

        settings = get_settings()
        settings.audio_cache_path.mkdir(parents=True, exist_ok=True)
        name = f"{prefix}_{hashlib.md5(text.encode()).hexdigest()}.wav"
        path = settings.audio_cache_path / name
        if not path.exists():
            audio = await tts.synthesize(text)

            def _write():
                sf.write(str(path), audio.pcm, audio.sample_rate, subtype="PCM_16")

            await asyncio.to_thread(_write)
        return path
    except Exception as exc:
        log.warning("synthesize_failed", error=str(exc))
        return None
