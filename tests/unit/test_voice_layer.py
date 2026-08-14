"""Voice layer unit tests. No network, no API keys."""

from __future__ import annotations

import numpy as np
import pytest

from outbound_ai.common.arabic import contains_arabic, normalize_arabic, normalize_light
from outbound_ai.voice.audio_utils import (
    PCMStreamAssembler,
    chunk_to_wav_bytes,
    concat,
    from_gradio,
    resample,
    to_int16,
    to_mono,
)
from outbound_ai.voice.base import SAMPLE_RATE, AudioChunk
from outbound_ai.voice.text_stream import as_async_stream, sentence_chunker, split_segments
from outbound_ai.voice.vad import ManualEndpointing
from tests.fixtures.fake_voice import FakeSTT, FakeTTS, silence, tone

# --------------------------------------------------------------------------- Arabic


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("نَعَم", "نعم"),  # diacritics stripped
        ("نعـــم", "نعم"),  # tatweel stripped
        ("أيوة", "ايوه"),  # alef + ta marbuta unified
        ("إيه", "ايه"),
        ("مصطفى", "مصطفي"),  # alef maqsura -> ya
        ("تذكرة رقم ١٢٣", "تذكره رقم 123"),  # Arabic-Indic digits -> ASCII
        ("  مرحبا   بك  ", "مرحبا بك"),  # whitespace collapsed
        ("", ""),
    ],
)
def test_normalize_arabic(raw: str, expected: str) -> None:
    assert normalize_arabic(raw) == expected


def test_normalized_spellings_of_yes_converge() -> None:
    """The whole point: the classifier must see one string, not five."""
    assert normalize_arabic("أيوة") == normalize_arabic("ايوه") == normalize_arabic("أيوه")


def test_normalize_light_preserves_letter_forms() -> None:
    """Text that a human reads or a voice speaks must keep correct orthography."""
    assert normalize_light("المشكلةُ اتحلت") == "المشكلة اتحلت"


def test_contains_arabic() -> None:
    assert contains_arabic("ticket رقم 5")
    assert not contains_arabic("ticket 5")


# ---------------------------------------------------------------------------- Audio


def test_audio_chunk_rejects_stereo() -> None:
    with pytest.raises(ValueError, match="mono"):
        AudioChunk(pcm=np.zeros((10, 2), dtype=np.int16))


def test_audio_chunk_rejects_float() -> None:
    with pytest.raises(ValueError, match="int16"):
        AudioChunk(pcm=np.zeros(10, dtype=np.float32))


def test_duration_and_silence() -> None:
    assert silence(500).duration_ms == 500
    assert silence(500).is_silent
    assert not tone(500).is_silent


def test_to_mono_and_to_int16() -> None:
    assert to_mono(np.zeros((8, 2))).shape == (8,)
    assert to_int16(np.array([1.0, -1.0], dtype=np.float32)).tolist() == [32767, -32767]


def test_to_int16_clips_instead_of_wrapping() -> None:
    """Overshoot must saturate. Wrapping turns a loud sample into a loud opposite-sign
    sample, which is audible as a click and confuses VAD later."""
    assert to_int16(np.array([2.0, -2.0], dtype=np.float32)).tolist() == [32767, -32768]


def test_resample_changes_length_proportionally() -> None:
    out = resample(tone(1000, sample_rate=48_000).pcm, 48_000, 16_000)
    assert abs(len(out) - 16_000) < 50
    assert out.dtype == np.int16


def test_resample_noop_when_rates_match() -> None:
    pcm = tone(100).pcm
    assert np.array_equal(resample(pcm, SAMPLE_RATE, SAMPLE_RATE), pcm)


def test_from_gradio_normalizes_stereo_float_48k() -> None:
    stereo = np.zeros((48_000, 2), dtype=np.float32)
    stereo[:, 0] = 0.5
    chunk = from_gradio((48_000, stereo))
    assert chunk is not None
    assert chunk.sample_rate == SAMPLE_RATE
    assert chunk.pcm.dtype == np.int16
    assert abs(chunk.duration_ms - 1000) < 10


def test_from_gradio_handles_empty() -> None:
    assert from_gradio(None) is None
    assert from_gradio((16_000, np.zeros(0, dtype=np.int16))) is None


def test_wav_roundtrip_has_header() -> None:
    assert chunk_to_wav_bytes(tone(100))[:4] == b"RIFF"


def test_concat_rejects_mixed_rates() -> None:
    with pytest.raises(ValueError, match="sample rates"):
        concat([silence(10), silence(10, sample_rate=8000)])


def test_pcm_assembler_carries_odd_byte_across_chunks() -> None:
    """A chunk boundary landing mid-sample must not shift every later sample by a byte."""
    original = np.array([100, -200, 300, -400], dtype="<i2")
    raw = original.tobytes()
    assembler = PCMStreamAssembler()

    first = assembler.push(raw[:3])  # 1.5 samples
    second = assembler.push(raw[3:])
    rebuilt = np.concatenate([c.pcm for c in (first, second) if c is not None])

    assert np.array_equal(rebuilt, original)


def test_pcm_assembler_flush_drops_half_sample() -> None:
    assembler = PCMStreamAssembler()
    assert assembler.push(b"\x01") is None
    assert assembler.flush() is None


# --------------------------------------------------------------------- Text chunking


def test_split_segments_breaks_on_arabic_punctuation() -> None:
    text = "صباح الخير معاك نظام المتابعة. عايز أتأكد إن المشكلة اتحلت؟"
    segments = split_segments(text)
    assert len(segments) == 2
    assert segments[0].endswith(".")
    assert segments[1].endswith("؟")


def test_split_segments_holds_short_fragments() -> None:
    """`نعم،` alone is not worth a TTS request — it must merge with what follows."""
    assert len(split_segments("نعم، تمام كده يا فندم والمشكلة اتحلت خلاص.")) == 1


def test_split_segments_force_flushes_a_run_on_sentence() -> None:
    assert len(split_segments("كلمة " * 60)) > 1


async def test_sentence_chunker_yields_before_stream_ends() -> None:
    tokens = ["صباح ", "الخير ", "معاك ", "نظام ", "المتابعة", ". ", "إزيك ", "النهارده", "؟"]
    segments = [seg async for seg in sentence_chunker(as_async_stream(tokens))]
    assert len(segments) == 2
    assert segments[0].startswith("صباح")


async def test_sentence_chunker_flushes_tail_without_punctuation() -> None:
    segments = [seg async for seg in sentence_chunker(as_async_stream(["مرحبا ", "بك"]))]
    assert segments == ["مرحبا بك"]


async def test_sentence_chunker_ignores_empty_tokens() -> None:
    segments = [seg async for seg in sentence_chunker(as_async_stream(["", "مرحبا بك", ""]))]
    assert segments == ["مرحبا بك"]


# ---------------------------------------------------------------------------- Fakes


async def test_fake_stt_returns_both_text_forms() -> None:
    stt = FakeSTT(["أيوة المشكلة اتحلت"])
    result = await stt.transcribe(tone(1000), vocabulary_hints=["تذكرة 42"])

    assert result.text_raw == "أيوة المشكلة اتحلت"
    assert result.text_norm == "ايوه المشكله اتحلت"
    assert not result.is_empty
    assert stt.calls[0][1] == ["تذكرة 42"]


async def test_fake_stt_empty_when_script_exhausted() -> None:
    assert (await FakeSTT().transcribe(tone(500))).is_empty


async def test_fake_tts_stream_records_segments() -> None:
    tts = FakeTTS()
    chunks = [c async for c in tts.stream(as_async_stream(["مرحبا بك في الخدمة", "؟"]))]

    assert len(chunks) == 1
    assert tts.spoken == ["مرحبا بك في الخدمة؟"]
    assert chunks[0].duration_ms > 0


# ----------------------------------------------------------------------- Endpointing


async def test_manual_endpointing_delivers_submitted_audio() -> None:
    endpointing = ManualEndpointing()
    endpointing.submit(tone(700))
    assert (await endpointing.wait_for_end_of_speech(timeout_s=1)).duration_ms == 700


async def test_manual_endpointing_reset_discards_buffer() -> None:
    endpointing = ManualEndpointing()
    endpointing.submit(tone(700))
    endpointing.reset()

    with pytest.raises(TimeoutError):
        await endpointing.wait_for_end_of_speech(timeout_s=0.05)
