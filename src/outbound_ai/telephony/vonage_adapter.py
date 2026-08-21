"""Vonage telephony adapter — real outbound calling via Vonage's Voice API.

IMPLEMENTATION NOTE: pyproject.toml pins vonage>=4.8.2 (SDK v4), which is a
ground-up rewrite using per-API pydantic models. This adapter deliberately
does NOT use vonage_client.voice.create_call(...) because the exact v4
request/response model names for the Voice API couldn't be confirmed at the
time this was written — guessing at an unverified model risks code that
looks right and breaks at runtime. Instead this calls the REST Voice API
directly via httpx (already a dependency), authenticated with a JWT built
by vonage_jwt.JwtClient — both of those are independently confirmed, stable
building blocks regardless of which SDK version is installed. If you later
confirm the v4 SDK's voice model shape, swapping these httpx calls for the
SDK's own methods is a contained change — nothing outside this file needs
to know either way, per the port/adapter split in port.py.

AUDIO NOTE: this adapter only places/ends/transfers calls — it does not
bridge call audio to STTPort/TTSPort. Vonage streams live call audio over a
WebSocket action referenced in the NCCO returned by your answer_url webhook.
That WebSocket endpoint (and the answer_url/event_url webhook routes
themselves) need to live in api/ once FastAPI exists — not yet built. Until
then, this adapter can dial and hang up real calls, but nothing will
actually bridge the STT/TTS pipeline to the live call audio.
"""
from __future__ import annotations

import time
import uuid

import httpx
import structlog
from vonage_jwt import JwtClient

from outbound_ai.config.settings import get_settings
from outbound_ai.telephony.port import (
    CallFailedError,
    CallSession,
    CallStatus,
    TelephonyPort,
)

log = structlog.get_logger(__name__)

_VOICE_API_BASE = "https://api.nexmo.com/v1/calls"


class VonageTelephonyAdapter(TelephonyPort):
    def __init__(self) -> None:
        settings = get_settings()
        self._settings = settings
        private_key = settings.vonage_private_key_full_path.read_text()
        self._jwt_client = JwtClient(
            application_id=settings.vonage_application_id,
            private_key=private_key,
        )
        self._active_calls: dict[str, CallSession] = {}

    def _auth_headers(self) -> dict[str, str]:
        # Short-lived JWT per request rather than a cached long-lived one —
        # Voice API JWTs default to 15 min if no exp claim is set; minting
        # fresh avoids ever using one that's about to expire mid-call-setup.
        token = self._jwt_client.generate_application_jwt({})
        # generate_application_jwt() returns bytes, not str — f-string
        # formatting bytes directly embeds its repr (b'...', quotes and
        # all) into the header instead of the actual token, which Vonage
        # correctly rejects as garbage. Decode explicitly.
        if isinstance(token, bytes):
            token = token.decode("utf-8")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async def place_call(self, to_number: str, from_number: str) -> CallSession:
        answer_url = f"{self._settings.public_webhook_base_url}/telephony/vonage/answer"
        event_url = f"{self._settings.public_webhook_base_url}/telephony/vonage/event"

        payload = {
            "to": [{"type": "phone", "number": to_number.lstrip("+")}],
            "from": {"type": "phone", "number": from_number.lstrip("+")},
            "ncco": [
                {
                    "action": "talk",
                    "text": "مرحبا، معك المساعد الالي بخصوص تذكرتك المفتوحة. من فضلك اشرح مشكلتك بعد الصافرة.",
                    "language": "ar",
                },
                {
                    "action": "record",
                    "eventUrl": [f"{self._settings.public_webhook_base_url}/telephony/vonage/recording"],
                    "endOnSilence": 3,
                    "beepStart": True,
                },
                {"action": "talk", "text": "شكرا لك، سيتم التواصل معك قريبا.", "language": "ar"},
            ],
            "event_url": [f"{self._settings.public_webhook_base_url}/telephony/vonage/event"],
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                _VOICE_API_BASE, json=payload, headers=self._auth_headers(), timeout=10.0
            )

        if response.status_code not in (200, 201):
            log.error("vonage_place_call_failed", status=response.status_code, body=response.text)
            raise CallFailedError(f"Vonage call creation failed: {response.status_code} {response.text}")

        data = response.json()
        call_id = data.get("uuid", str(uuid.uuid4()))
        session = CallSession(
            call_id=call_id,
            to_number=to_number,
            from_number=from_number,
            status=CallStatus.RINGING,
        )
        self._active_calls[call_id] = session
        log.info("vonage_call_placed", call_id=call_id, to=to_number)
        return session

    async def hang_up(self, call_id: str) -> None:
        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{_VOICE_API_BASE}/{call_id}",
                json={"action": "hangup"},
                headers=self._auth_headers(),
                timeout=10.0,
            )
        if response.status_code not in (200, 204):
            log.error("vonage_hangup_failed", call_id=call_id, status=response.status_code)
        session = self._active_calls.pop(call_id, None)
        if session is not None:
            session.status = CallStatus.COMPLETED

    async def transfer_to_human(self, call_id: str, target_number: str) -> None:
        # Transfers a live call by pointing it at a new NCCO that connects
        # to the human agent's number. Requires api/ to serve that NCCO at
        # the referenced URL — same gap as the audio-bridging note above.
        transfer_ncco_url = (
            f"{self._settings.public_webhook_base_url}"
            f"/telephony/vonage/transfer?target={target_number}"
        )
        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{_VOICE_API_BASE}/{call_id}",
                json={"action": "transfer", "destination": {"type": "ncco", "url": [transfer_ncco_url]}},
                headers=self._auth_headers(),
                timeout=10.0,
            )
        if response.status_code not in (200, 204):
            log.error("vonage_transfer_failed", call_id=call_id, status=response.status_code)
            raise CallFailedError(f"Vonage transfer failed: {response.status_code} {response.text}")

    async def update_call_ncco(self, call_id: str, ncco: list) -> None:
        """Push a new NCCO into a live call — this is what makes multi-turn
        dialogue possible without WebSocket audio streaming."""
        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{_VOICE_API_BASE}/{call_id}",
                json={"action": "transfer", "destination": {"type": "ncco", "ncco": ncco}},
                headers=self._auth_headers(),
                timeout=15.0,
            )
        if response.status_code not in (200, 204):
            log.error("vonage_ncco_update_failed", call_id=call_id, status=response.status_code, body=response.text)

    async def place_call_with_ncco(self, to_number: str, from_number: str, ncco: list):
        """Place a call with a caller-supplied NCCO. Returns (CallSession, conversation_uuid)."""
        payload = {
            "to": [{"type": "phone", "number": to_number.lstrip("+")}],
            "from": {"type": "phone", "number": from_number.lstrip("+")},
            "ncco": ncco,
            "event_url": [f"{self._settings.public_webhook_base_url}/telephony/vonage/event"],
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(
                _VOICE_API_BASE, json=payload, headers=self._auth_headers(), timeout=15.0
            )
        if response.status_code not in (200, 201):
            raise CallFailedError(f"{response.status_code} {response.text}")
        data = response.json()
        session = CallSession(
            call_id=data["uuid"], to_number=to_number,
            from_number=from_number, status=CallStatus.RINGING,
        )
        self._active_calls[session.call_id] = session
        return session, data.get("conversation_uuid")
