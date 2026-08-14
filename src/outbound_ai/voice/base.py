"""Voice layer ports.

Agents, graph nodes and UI tabs depend on these abstractions only. Swapping Whisper for
Azure Speech, or ElevenLabs for a local model, means adding an adapter here — nothing
upstream changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass

import numpy as np
from pydantic import BaseModel, Field

# Canonical internal audio format. Whisper wants 16 kHz mono; ElevenLabs `pcm_16000`
# emits the same. Keeping one rate everywhere means resampling happens exactly once,
# at the microphone boundary.
SAMPLE_RATE = 16_000


class VoiceError(Exception):
    """Base class for voice layer failures."""


class STTError(VoiceError):
    """Transcription failed after retries."""


class TTSError(VoiceError):
    """Speech synthesis failed after retries."""


class VoiceConfigError(VoiceError):
    """A required credential or voice id is missing."""


@dataclass(slots=True)
class AudioChunk:
    """A block of mono 16-bit PCM audio."""

    pcm: np.ndarray  # int16, shape (n_samples,)
    sample_rate: int = SAMPLE_RATE

    def __post_init__(self) -> None:
        if self.pcm.ndim != 1:
            raise ValueError(f"AudioChunk expects mono 1-D audio, got shape {self.pcm.shape}")
        if self.pcm.dtype != np.int16:
            raise ValueError(f"AudioChunk expects int16 PCM, got {self.pcm.dtype}")

    @property
    def duration_ms(self) -> int:
        return int(len(self.pcm) * 1000 / self.sample_rate)

    @property
    def is_silent(self) -> bool:
        return len(self.pcm) == 0 or not bool(np.any(self.pcm))

    def as_gradio(self) -> tuple[int, np.ndarray]:
        """The `(sample_rate, samples)` tuple gr.Audio consumes."""
        return self.sample_rate, self.pcm


class TranscriptionResult(BaseModel):
    """Output of an STT turn.

    Two texts on purpose: `text_raw` is what the customer actually said and is what goes
    into the transcript and the QA report; `text_norm` is the normalized form fed to the
    intent classifier and to sparse retrieval. Never overwrite the raw text.
    """

    text_raw: str
    text_norm: str
    language: str = "ar"
    duration_ms: int = 0
    model: str = ""
    latency_ms: int = 0

    @property
    def is_empty(self) -> bool:
        return not self.text_norm.strip()


class SpeechSegment(BaseModel):
    """A piece of text handed to TTS, with the metadata the UI needs to show it."""

    text: str
    is_final: bool = False
    index: int = Field(default=0, ge=0)


class STTPort(ABC):
    """Speech to text."""

    @abstractmethod
    async def transcribe(
        self,
        audio: AudioChunk,
        *,
        vocabulary_hints: list[str] | None = None,
    ) -> TranscriptionResult:
        """Transcribe one customer turn.

        `vocabulary_hints` biases decoding toward domain terms (product names, the ticket
        id, procedure vocabulary). It is built per call from the ticket row and is the
        cheapest accuracy win available — without it, mixed Arabic/English product names
        transcribe differently on every call.
        """


class TTSPort(ABC):
    """Text to speech."""

    @abstractmethod
    async def synthesize(self, text: str, *, high_quality: bool = False) -> AudioChunk:
        """Render a complete utterance in one shot. Used for cached static prompts."""

    @abstractmethod
    async def stream(self, text_stream: AsyncIterator[str]) -> AsyncIterator[AudioChunk]:
        """Render a token stream to audio chunks as the text arrives.

        The implementation is responsible for buffering tokens into sentence-sized
        segments before hitting the API — see `voice.text_stream.sentence_chunker`.
        """


class EndpointingPort(ABC):
    """Decides when the customer has finished speaking.

    Push-to-talk resolves this from an explicit UI event. Real telephony will resolve it
    from voice activity detection. Isolating it here is what keeps the Twilio migration
    from touching graph code.
    """

    @abstractmethod
    async def wait_for_end_of_speech(self, timeout_s: float | None = None) -> AudioChunk:
        """Block until a complete customer utterance is available."""

    @abstractmethod
    def reset(self) -> None:
        """Discard any buffered audio. Called between turns."""
