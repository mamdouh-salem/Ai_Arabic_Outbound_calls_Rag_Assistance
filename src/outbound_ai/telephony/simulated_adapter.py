"""Simulated telephony adapter — no real dialing, no network calls. Every
call is instantly ANSWERED so the rest of the pipeline (STT/TTS/graph) can
be tested without Vonage credentials or a public webhook URL. This is what
smoke_test_graph.py and smoke_test_graph_real.py should use going forward
for the telephony layer, same role the Fake* classes play for voice ports.
"""
from __future__ import annotations

import uuid

from outbound_ai.telephony.port import CallSession, CallStatus, TelephonyPort


class SimulatedTelephonyAdapter(TelephonyPort):
    def __init__(self) -> None:
        self._active_calls: dict[str, CallSession] = {}

    async def place_call(self, to_number: str, from_number: str) -> CallSession:
        call_id = str(uuid.uuid4())
        session = CallSession(
            call_id=call_id,
            to_number=to_number,
            from_number=from_number,
            status=CallStatus.ANSWERED,
        )
        self._active_calls[call_id] = session
        return session

    async def hang_up(self, call_id: str) -> None:
        session = self._active_calls.pop(call_id, None)
        if session is not None:
            session.status = CallStatus.COMPLETED

    async def transfer_to_human(self, call_id: str, target_number: str) -> None:
        # No-op in simulation — nothing to actually transfer.
        return None
