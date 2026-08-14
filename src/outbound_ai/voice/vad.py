"""Endpointing: deciding when the customer has stopped talking.

Push-to-talk answers this from an explicit UI event, so v1 needs no voice activity
detection at all. It still goes behind `EndpointingPort` because real telephony has no
button — when the Twilio adapter lands, a VAD implementation is bound here and no graph
node changes.
"""

from __future__ import annotations

import asyncio

from outbound_ai.voice.base import AudioChunk, EndpointingPort


class ManualEndpointing(EndpointingPort):
    """Push-to-talk. The UI decides where the utterance ends.

    A side effect worth naming: because the talk button is disabled while the agent's
    audio is playing, the customer physically cannot interrupt. Barge-in is not handled
    here — it is structurally impossible, which is why v1 needs no interruption logic.
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[AudioChunk] = asyncio.Queue()

    def submit(self, audio: AudioChunk) -> None:
        """Called by the UI when the talk button is released."""
        self._queue.put_nowait(audio)

    async def wait_for_end_of_speech(self, timeout_s: float | None = None) -> AudioChunk:
        if timeout_s is None:
            return await self._queue.get()
        return await asyncio.wait_for(self._queue.get(), timeout=timeout_s)

    def reset(self) -> None:
        while not self._queue.empty():
            self._queue.get_nowait()


class SileroEndpointing(EndpointingPort):
    """Placeholder for the telephony path.

    Deliberately unimplemented: building VAD now would mean tuning silence thresholds
    against simulated audio that has none of the characteristics of a real phone line
    (8 kHz codec, network jitter, background noise). It is written against real call
    audio or not at all.
    """

    async def wait_for_end_of_speech(self, timeout_s: float | None = None) -> AudioChunk:
        raise NotImplementedError("VAD endpointing lands with the Twilio adapter")

    def reset(self) -> None:
        raise NotImplementedError("VAD endpointing lands with the Twilio adapter")
