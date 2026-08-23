"""Zero-argument graph factory for LangGraph Studio (`langgraph dev`).

Studio requires a module-path:attribute factory returning a compiled graph.
This wiring uses the REAL agents (Gemini intent classification, real Supabase
RAG retrieval/generation, real reporting/routing prompts) so stepping through
the graph in Studio reflects production behavior — only the audio hardware
ports (STT/TTS/endpointing) are faked, since a browser IDE can't play phone
audio anyway.

Run from the repo root:
    pip install -U "langgraph-cli[inmem]"
    langgraph dev
Then open the printed Studio URL.
"""
from __future__ import annotations

import numpy as np

from outbound_ai.graph.build import build_graph
from outbound_ai.graph.deps import GraphDependencies
from outbound_ai.voice.base import (
    AudioChunk,
    EndpointingPort,
    STTPort,
    TranscriptionResult,
    TTSPort,
)

_SILENCE = AudioChunk(pcm=np.zeros(1600, dtype=np.int16))


class StudioSilentSTT(STTPort):
    """The 'caller' utterance is provided by Studio's state editor instead of
    a microphone."""

    async def transcribe(self, audio, *, vocabulary_hints=None):
        return TranscriptionResult(text_raw="(studio input)", text_norm="(studio input)",
                                   model="studio-stt")


class StudioSilentTTS(TTSPort):
    async def synthesize(self, text, *, high_quality=False):
        return _SILENCE

    async def stream(self, text_stream):
        async for _ in text_stream:
            yield _SILENCE


class StudioSilentEndpointing(EndpointingPort):
    async def wait_for_end_of_speech(self, timeout_s=None):
        return _SILENCE

    def reset(self):
        pass


def build_studio_graph():
    """Compiled LangGraph wired for interactive Studio sessions."""
    from outbound_ai.agents import intent_classifier, kb_assist, reporting, routing

    deps = GraphDependencies(
        stt=StudioSilentSTT(),
        tts=StudioSilentTTS(),
        endpointing=StudioSilentEndpointing(),
        # real RAG pipeline (Egyptian troubleshooting style)
        kb_retrieve=kb_assist.retrieve,
        intent_classify=intent_classifier.classify,
        report=reporting.summarize,
        route=routing.escalate,
    )
    return build_graph(deps)
