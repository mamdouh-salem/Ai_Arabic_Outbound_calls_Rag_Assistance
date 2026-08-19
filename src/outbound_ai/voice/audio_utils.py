"""Audio format plumbing.

This module is the *only* place that resamples, mixes down or re-encodes audio. The rest
of the system assumes everything is already 16 kHz mono int16 (`voice.base.SAMPLE_RATE`).
"""

from __future__ import annotations

import io
from math import gcd

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from outbound_ai.voice.base import SAMPLE_RATE, AudioChunk

_INT16_MAX = 32767


def to_mono(samples: np.ndarray) -> np.ndarray:
    """Mix any channel layout down to 1-D."""
    if samples.ndim == 1:
        return samples
    return samples.mean(axis=1)


def to_int16(samples: np.ndarray) -> np.ndarray:
    """Convert float (-1..1) or wider int audio to int16, clipping rather than wrapping."""
    if samples.dtype == np.int16:
        return samples
    if np.issubdtype(samples.dtype, np.floating):
        return np.clip(samples * _INT16_MAX, -_INT16_MAX - 1, _INT16_MAX).astype(np.int16)
    if samples.dtype == np.int32:
        return (samples >> 16).astype(np.int16)
    if samples.dtype == np.uint8:
        return ((samples.astype(np.int16) - 128) << 8).astype(np.int16)
    return samples.astype(np.int16)


def resample(samples: np.ndarray, sr_in: int, sr_out: int = SAMPLE_RATE) -> np.ndarray:
    """Anti-aliased rational resampling.

    Browsers hand us 44.1 or 48 kHz; Whisper wants 16 kHz. Naive decimation (np.interp,
    slicing) aliases high frequencies down into the speech band and measurably hurts
    transcription, so this uses a polyphase filter.
    """
    if sr_in == sr_out or len(samples) == 0:
        return samples
    divisor = gcd(int(sr_in), int(sr_out))
    up, down = sr_out // divisor, sr_in // divisor
    resampled = resample_poly(samples.astype(np.float64), up, down)
    return to_int16(np.clip(resampled / _INT16_MAX, -1.0, 1.0))


def from_gradio(audio: tuple[int, np.ndarray] | None) -> AudioChunk | None:
    """Normalize whatever `gr.Audio(type="numpy")` hands us into an AudioChunk.

    Gradio yields `(sample_rate, samples)` where samples may be stereo, float32 or int32
    depending on the browser and the microphone.
    """
    if audio is None:
        return None
    sample_rate, samples = audio
    if samples is None or len(samples) == 0:
        return None
    mono = to_int16(to_mono(np.asarray(samples)))
    return AudioChunk(pcm=resample(mono, sample_rate, SAMPLE_RATE), sample_rate=SAMPLE_RATE)


def pcm_bytes_to_chunk(raw: bytes, sample_rate: int = SAMPLE_RATE) -> AudioChunk:
    """Wrap raw little-endian int16 PCM (what ElevenLabs `pcm_*` formats return)."""
    return AudioChunk(pcm=np.frombuffer(raw, dtype="<i2").copy(), sample_rate=sample_rate)


def chunk_to_wav_bytes(chunk: AudioChunk) -> bytes:
    """Encode to an in-memory WAV file, which is what the Whisper endpoint accepts."""
    buffer = io.BytesIO()
    sf.write(buffer, chunk.pcm, chunk.sample_rate, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


def read_wav(path) -> AudioChunk:
    samples, sample_rate = sf.read(path, dtype="int16", always_2d=False)
    return AudioChunk(pcm=to_mono(samples).astype(np.int16), sample_rate=sample_rate)


def write_wav(path, chunk: AudioChunk) -> None:
    sf.write(path, chunk.pcm, chunk.sample_rate, format="WAV", subtype="PCM_16")


def concat(chunks: list[AudioChunk]) -> AudioChunk:
    """Join chunks that share a sample rate into one buffer."""
    if not chunks:
        return AudioChunk(pcm=np.zeros(0, dtype=np.int16))
    rates = {c.sample_rate for c in chunks}
    if len(rates) > 1:
        raise ValueError(f"cannot concatenate mixed sample rates: {sorted(rates)}")
    return AudioChunk(
        pcm=np.concatenate([c.pcm for c in chunks]),
        sample_rate=chunks[0].sample_rate,
    )


class PCMStreamAssembler:
    """Turns a byte stream into whole-sample AudioChunks.

    HTTP chunk boundaries do not respect sample boundaries: a chunk can end mid-sample,
    on an odd byte count. Interpreting that directly as int16 shifts every subsequent
    sample by one byte and turns the rest of the utterance into noise. This carries the
    stray byte over to the next chunk.
    """

    def __init__(self, sample_rate: int = SAMPLE_RATE) -> None:
        self.sample_rate = sample_rate
        self._remainder = b""

    def push(self, raw: bytes) -> AudioChunk | None:
        buffer = self._remainder + raw
        usable = len(buffer) - (len(buffer) % 2)
        if usable == 0:
            self._remainder = buffer
            return None
        self._remainder = buffer[usable:]
        return pcm_bytes_to_chunk(buffer[:usable], self.sample_rate)

    def flush(self) -> AudioChunk | None:
        """Emit anything left over. A trailing odd byte is dropped — it is half a sample."""
        if len(self._remainder) < 2:
            self._remainder = b""
            return None
        chunk = self.push(b"")
        self._remainder = b""
        return chunk
