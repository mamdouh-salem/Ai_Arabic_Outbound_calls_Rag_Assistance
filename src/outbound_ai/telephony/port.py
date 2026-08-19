"""Telephony port.

Agents and graph nodes depend on this abstraction only. Swapping the
simulated adapter for Vonage means adding an adapter here — nothing
upstream changes.

SCOPE: this port establishes/ends/transfers the phone connection and
reports call status. It does NOT carry audio directly — audio flows through
voice/base.py's STTPort/TTSPort/EndpointingPort once a call is ANSWERED.
This split exists because "how audio physically reaches the call" is
telephony-provider-specific (Vonage bridges call audio over a WebSocket
action named in the NCCO, requiring a live WebSocket server — see
vonage_adapter.py's docstring) while "how audio is transcribed/synthesized"
is not, and is already built.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class CallStatus(str, Enum):
    RINGING = "ringing"
    ANSWERED = "answered"
    BUSY = "busy"
    NO_ANSWER = "no_answer"
    FAILED = "failed"
    COMPLETED = "completed"


class TelephonyError(Exception):
    """Base class for telephony layer failures."""


class CallFailedError(TelephonyError):
    """The call could not be placed or was rejected (busy/no-answer/provider error)."""


@dataclass(slots=True)
class CallSession:
    """A live or completed outbound call."""

    call_id: str
    to_number: str
    from_number: str
    status: CallStatus


class TelephonyPort(ABC):
    """Places and manages outbound calls."""

    @abstractmethod
    async def place_call(self, to_number: str, from_number: str) -> CallSession:
        """Dial `to_number`. Raises CallFailedError if the call can't be
        established. On success, returns a CallSession — the caller is
        responsible for waiting for it to reach ANSWERED before assuming
        audio ports (STT/TTS/Endpointing) are usable."""

    @abstractmethod
    async def hang_up(self, call_id: str) -> None:
        """End an active call."""

    @abstractmethod
    async def transfer_to_human(self, call_id: str, target_number: str) -> None:
        """Transfer a live call to a human agent's number — what
        agents/routing.py's escalation ultimately triggers."""
