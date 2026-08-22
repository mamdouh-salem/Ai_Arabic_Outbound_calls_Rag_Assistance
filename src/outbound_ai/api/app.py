"""Multi-turn Arabic outbound call agent + reporting."""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import google.generativeai as genai
import httpx
import structlog
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, EmailStr, Field
from supabase import create_client

from outbound_ai.agents import intent_classifier, kb_assist, reporting, routing
from outbound_ai.api.routers import admin_users, data, kb as kb_docs, workspaces
from outbound_ai.auth import AuthContext, get_current_user
from outbound_ai.auth.dependencies import AdminOrAbove, CurrentUser
from outbound_ai.config.settings import get_settings
from outbound_ai.telephony.vonage_adapter import VonageTelephonyAdapter

log = structlog.get_logger(__name__)
app = FastAPI(
    title="Arabic AI Outbound Call Agent",
    description="Multi-agent Arabic outbound call system with RAG knowledge assistant.",
    version="0.2.0",
    # Disable automatic docs in production — re-enable for dev via APP_ENV check
    docs_url="/docs" if get_settings().app_env == "dev" else None,
    redoc_url="/redoc" if get_settings().app_env == "dev" else None,
)
settings = get_settings()

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

# CORS — tighten allowed_origins before production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.app_env == "dev" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type", "X-Workspace-Id"],
)

_adapter = VonageTelephonyAdapter()
CALL_STATE = {}
HUMAN_AGENT_NUMBER = "+201211497586"
DEFAULT_WORKSPACE_ID = "aaaaaaaa-0000-0000-0000-000000000001"

# Front-end static assets (SPA served by this API — same origin, no CORS pain)
STATIC_DIR = Path(__file__).resolve().parent / "static"

# ---------------------------------------------------------------------------
# Live-call speech: prefer ElevenLabs (Egyptian voice) served as a WAV the
# NCCO <stream> action can play; fall back to Vonage's built-in TTS on any
# failure so a vendor hiccup never kills a live call.
# ---------------------------------------------------------------------------
_tts = None


def _get_tts():
    global _tts
    if _tts is None:
        try:
            from outbound_ai.voice.tts_elevenlabs import ElevenLabsTTS

            _tts = ElevenLabsTTS() or False
        except Exception as exc:
            log.warning("elevenlabs_unavailable", error=str(exc))
            _tts = False
    return _tts or None


async def speak(text: str) -> list[dict]:
    """NCCO actions that speak `text` — ElevenLabs WAV when possible."""
    tts = _get_tts()
    if tts:
        try:
            import hashlib

            import soundfile as sf

            audio = await tts.synthesize(text)
            name = f"call_{hashlib.md5(text.encode()).hexdigest()}.wav"
            path = settings.audio_cache_path / name
            settings.audio_cache_path.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                def _write():
                    sf.write(str(path), audio.pcm, audio.sample_rate, subtype="PCM_16")

                await asyncio.to_thread(_write)
            url = f"{_base()}/audio/{name}"
            return [{"action": "stream", "stream": [{"url": url, "loop": 1}]}]
        except Exception as exc:
            log.warning("elevenlabs_synthesis_failed", error=str(exc))
    return [{"action": "talk", "text": text, "language": "ar"}]


@app.get("/audio/{fname}", include_in_schema=False)
async def serve_audio(fname: str):
    """Public WAV endpoint Vonage streams during live calls."""
    safe = Path(fname).name  # no traversal
    path = settings.audio_cache_path / safe
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "audio not found")
    return FileResponse(path, media_type="audio/wav")

# ---------------------------------------------------------------------------
# Routers (auth, KB management, user management, data visibility)
# ---------------------------------------------------------------------------
app.include_router(kb_docs.router)
app.include_router(admin_users.router)
app.include_router(workspaces.router)
app.include_router(data.router)


def _base():
    return settings.public_webhook_base_url


# ---------------------------------------------------------------------------
# Health / auth probe  (demonstrates dependency injection)
# ---------------------------------------------------------------------------

@app.get("/health", tags=["ops"])
async def health_check():
    """Unauthenticated liveness probe — safe to hit from load-balancers."""
    return {"status": "ok", "version": app.version}


@app.get("/health/auth", tags=["ops"])
async def health_check_auth(ctx: CurrentUser):
    """Authenticated probe — validates JWT and returns resolved identity.

    Useful for frontend auth flows to confirm the token is valid and
    to surface the user's workspace + role without a separate /me endpoint.
    """
    return {
        "status": "ok",
        "user_id": str(ctx.user_id),
        "workspace_id": str(ctx.workspace_id) if ctx.workspace_id else None,
        "role": ctx.role.value,
        "email": ctx.email,
    }


@app.get("/api/config", tags=["ops"])
async def public_frontend_config():
    """Values the browser SPA needs before login. The anon key is public by
    design (it only allows unauthenticated auth endpoints + RLS-guarded reads)."""
    return {
        "supabase_url": settings.supabase_url,
        "anon_key": settings.supabase_anon_key.get_secret_value() if settings.supabase_anon_key else "",
    }


# ---------------------------------------------------------------------------
# Public self sign-up (agent role, default workspace)
# ---------------------------------------------------------------------------

class SignUpRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    display_name: str = Field(min_length=1, max_length=120)

@app.post("/auth/signup", tags=["auth"], status_code=status.HTTP_201_CREATED)
async def sign_up(body: SignUpRequest):
    """Open registration — new users join the 'default' workspace as agents.
    Admins promote them later; super admins move them between workspaces."""
    from outbound_ai.db.service_client import get_service_client

    sb = get_service_client()
    ws = (
        sb.table("workspaces").select("id").eq("slug", "default").limit(1).execute().data
    )
    if not ws:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "No default workspace exists yet.")
    try:
        created = sb.auth.admin.create_user({
            "email": body.email,
            "password": body.password,
            "email_confirm": True,
            "user_metadata": {"display_name": body.display_name},
        })
    except Exception as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Sign-up refused: {exc}") from exc
    uid = created.user.id
    try:
        sb.table("users").insert({
            "id": uid, "email": body.email,
            "display_name": body.display_name, "platform_role": "agent",
        }).execute()
        sb.table("workspace_members").insert({
            "workspace_id": ws[0]["id"], "user_id": uid, "role": "agent",
        }).execute()
    except Exception as exc:
        log.error("signup_profile_write_failed", user=uid, error=str(exc))
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"Account created but profile setup failed: {exc}",
        ) from exc
    return {"status": "created", "user_id": uid, "role": "agent",
            "workspace_id": ws[0]["id"]}



def _rec(stage):
    return {"action": "record",
            "eventUrl": [f"{_base()}/telephony/vonage/recording?stage={stage}"],
            "endOnSilence": 3, "endOnKey": "#", "beepStart": True}


def _hold():
    line = ("لحظة واحدة يا فندم، بشوف الموضوع ده حالاً. استنى معايا شوية من فضلك. "
            "شكراً لصبرك، جاري مراجعة بيانات الشكوى بتاعتك دلوقتي.")
    return [{"action": "talk", "text": line, "language": "ar"} for _ in range(5)]


def _transcribe(b):
    genai.configure(api_key=settings.gemini_api_key.get_secret_value())
    m = genai.GenerativeModel(settings.gemini_model)
    r = m.generate_content(["فرّغ التسجيل ده لنص عربي قصير. اكتب النص بس بدون أي شرح.",
                            {"mime_type": "audio/mpeg", "data": b}])
    return r.text.strip()


def _safe_uuid(v: str):
    """Return v if it's a valid uuid, else None — the calls.ticket_id /
    customer_id columns are uuid-typed, and free-text IDs like 'T-1001'
    must never reach them (this silently killed every report row before)."""
    try:
        import uuid as _uuid

        return str(_uuid.UUID(str(v)))
    except Exception:
        return None


async def _save(
    conv: str,
    state: dict,
    rep: dict,
    *,
    kb_answer: str | None = None,
    sources: list | None = None,
    escalation: dict | None = None,
) -> None:
    """Persist one call report — jsonl + Supabase `calls` row.

    Includes workspace_id / timestamps / duration; without workspace_id the
    insert violated its NOT NULL constraint and NOTHING ever showed up in
    the dashboard."""
    ctx = CALL_STATE.get(conv, {})
    ended = datetime.now(timezone.utc)
    started_iso = ctx.get("started_at") or ended.isoformat()
    try:
        started = datetime.fromisoformat(started_iso)
        duration_seconds = max(0, round((ended - started).total_seconds()))
    except ValueError:
        duration_seconds = None

    row = {
        "vonage_call_id": ctx.get("call_id"),
        "workspace_id": ctx.get("workspace_id") or DEFAULT_WORKSPACE_ID,
        "transcript": " | ".join(ctx.get("turns", [])),
        "intent": state.get("intent"),
        "kb_answer": kb_answer if kb_answer is not None else ctx.get("kb_answer"),
        "kb_sources": sources if sources else ctx.get("sources") or None,
        "kb_answer_given": bool(state.get("kb_answer_given")),
        "escalated": bool(state.get("escalated")),
        "escalation_reason": (escalation or {}).get("escalation_reason")
                             or state.get("escalation_reason"),
        "call_outcome": rep.get("call_outcome"),
        "call_summary": rep.get("call_summary"),
        "started_at": started_iso,
        "ended_at": ended.isoformat(),
        "duration_seconds": duration_seconds,
        "ticket_ref": ctx.get("ticket_id", "") or None,
    }
    tid = _safe_uuid(ctx.get("ticket_id", ""))
    if tid:
        row["ticket_id"] = tid

    Path("call_reports.jsonl").open("a", encoding="utf-8").write(
        json.dumps({"conv": conv, **row}, ensure_ascii=False, default=str) + "\n")
    try:
        sb = create_client(settings.supabase_url,
                           settings.supabase_service_role_key.get_secret_value())
        sb.table("calls").insert(row).execute()
        log.info("call_report_saved", conv=conv, duration=duration_seconds)
    except Exception as e:
        log.error("supabase_save_failed", error=str(e))


@app.post("/start-call")
async def start_call(request: Request, ctx: AdminOrAbove):
    """Place a live outbound call. admin/super_admin only — dialing costs
    money and is a campaign-level action."""
    b = await request.json()
    log.info("start_call", by_user=str(ctx.user_id), to=b.get("phone"))
    if not settings.vonage_from_number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="VONAGE_FROM_NUMBER is not configured in .env — add your Vonage "
                   "virtual number (Dashboard → Numbers) and restart the API.",
        )
    title = b.get("ticket_title", "شكوتك")
    greeting = (
        f"السلام عليكم، معك المساعد الآلي من خدمة العملاء. "
        f"أنا بكلمك دلوقتي بخصوص المشكلة بتاعتك، وهي {title}. "
        f"عايز أطمن بس: هل المشكلة دي اتحلت ولا لسه؟ اتكلم بعد الصفارة."
    )
    ncco = [await speak(greeting)] + [_rec(1), *_hold()]
    session, conv = await _adapter.place_call_with_ncco(
        to_number=b["phone"], from_number=settings.vonage_from_number.lstrip("+"), ncco=ncco)
    CALL_STATE[conv] = {
        "conv": conv,
        "call_id": session.call_id,
        "ticket_id": b.get("ticket_id", ""),
        "ticket_title": title,
        "category": b.get("category", "billing"),
        "transcript": [],
        "turns": [],
        "stage": 1,
        "workspace_id": str(ctx.workspace_id) if ctx.workspace_id else DEFAULT_WORKSPACE_ID,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    log.info("call_started", call_id=session.call_id, conv=conv)
    return {"call_id": session.call_id, "conversation_uuid": conv}


@app.post("/telephony/vonage/event")
async def event(request: Request):
    b = await request.json()
    conv, uuid = b.get("conversation_uuid"), b.get("uuid")
    if conv and uuid and conv in CALL_STATE:
        CALL_STATE[conv]["call_id"] = uuid
    log.info("vonage_event", status=b.get("status"))
    return {}


_RESOLVED_WORDS = ("اتحلت", "تحلت", "خلاص", "تمام", "أهو", "اهو", "اشتغلت", "شغالة")
_DONE_WORDS = ("خلصت", "خلص", "عملتها", "عملت كده", "سويت")


def _says(text: str, words) -> bool:
    return any(w in text for w in words)


@app.post("/telephony/vonage/recording")
async def recording(request: Request):
    b = await request.json()
    stage = int(request.query_params.get("stage", "1"))
    conv, url = b.get("conversation_uuid"), b.get("recording_url")
    ctx = CALL_STATE.get(conv, {})
    call_id = ctx.get("call_id")
    if not url or not call_id:
        return {}

    # Vonage can fire the same recording webhook more than once for the same
    # stage/call — without this guard, every retry re-transcribes, re-runs
    # the whole intent/KB/reporting pipeline, and writes a fresh near-duplicate
    # row to call_reports.jsonl + Supabase (this was the "same words logged
    # twice, 11 seconds apart" issue).
    processed = ctx.setdefault("processed_stages", set())
    if stage in processed:
        log.warning("duplicate_recording_webhook", call_id=call_id, stage=stage)
        return {}
    processed.add(stage)

    log.info("recording", stage=stage, call_id=call_id)
    async with httpx.AsyncClient() as c:
        audio = (await c.get(url, headers=_adapter._auth_headers(), timeout=20.0)).content
    text = _transcribe(audio)
    log.info("transcribed", stage=stage, text=text)

    tr = ctx.get("transcript", []) + [HumanMessage(content=text)]
    ctx["transcript"] = tr
    ctx.setdefault("turns", []).append(text)
    cat, title = ctx.get("category", "billing"), ctx.get("ticket_title", "")
    flow_stage = ctx.get("stage", 1)

    async def _close(outcome_state: dict):
        rep = await reporting.summarize(outcome_state)
        await _save(conv, outcome_state, rep)
        return {}

    # ---- customer asks for a human at ANY point --------------------------
    intent = await intent_classifier.classify(tr)
    log.info("intent", intent=intent, stage=flow_stage)
    if intent == "wants_human":
        return await _transfer_to_human(ctx, call_id, tr, {"intent": intent,
            "kb_category": cat, "ticket_id": ctx.get("ticket_id", ""),
            "kb_answer_given": ctx.get("kb_answer_given", False), "transcript": tr})

    # ---- STAGE 1: first answer to "did it get resolved?" -----------------
    if flow_stage == 1:
        if intent == "resolved":
            ncco = [await speak(
                "تمام الحمد لله، مبسوط إن المشكلة اتحلت. شكراً لوقتك، مع السلامة.")]
            await _adapter.update_call_ncco(call_id, ncco)
            return await _close({"intent": "resolved", "kb_answer_given": True,
                                 "escalated": False, "transcript": tr})

        # unresolved/unclear → KB-guided troubleshooting step
        query = f"{title} {text}".strip()
        ans, chunks, ok = await kb_assist.retrieve(
            query, cat, style="call",
            ticket_context=f"المشكلة المسجلة في التذكرة: {title}")
        rep1 = await reporting.summarize({"intent": intent, "kb_answer_given": ok,
                                          "escalated": False, "transcript": tr})
        await _save(conv, {"intent": intent, "kb_answer_given": ok,
                           "escalated": False, "transcript": tr}, rep1,
                    kb_answer=ans, sources=[c.get("source") for c in chunks])
        ctx.update({"kb_answer": ans, "sources": [c.get("source") for c in chunks],
                    "kb_answer_given": ok})
        tr.append(AIMessage(content=ans))
        followup = (
            f"{ans}" if ok else ans
        )
        spoken = followup if ans.endswith("قولّي خلصت.") or ans.endswith("قولي خلصت") \
            else f"{ans} لما تخلص قولّي خلصت."
        ncco = [await speak(spoken)] + [_rec(2), *_hold()]
        ctx["stage"] = 2
        await _adapter.update_call_ncco(call_id, ncco)
        return {}

    # ---- STAGE 2: customer says they finished the step -------------------
    if flow_stage == 2:
        if _says(text, _DONE_WORDS) or intent in ("resolved", "unclear"):
            ask = await speak("طب إيه، المشكلة اتحلت معاك ولا لسه؟")
            ncco = list(ask) + [_rec(3), *_hold()]
            ctx["stage"] = 3
            await _adapter.update_call_ncco(call_id, ncco)
            return {}
        # still mid-step or something else → re-run KB with their new words
        ans, chunks, ok = await kb_assist.retrieve(
            f"{title} {text}", cat, style="call",
            ticket_context=f"المشكلة المسجلة في التذكرة: {title}")
        spoken = ans if ans.endswith(("خلصت.", "خلصت")) else f"{ans} لما تخلص قولّي خلصت."
        ncco = [await speak(spoken)] + [_rec(2), *_hold()]
        await _adapter.update_call_ncco(call_id, ncco)
        return {}

    # ---- STAGE 3: final resolution verdict --------------------------------
    resolved_now = _says(text, _RESOLVED_WORDS) or intent == "resolved"
    if resolved_now:
        ncco = [await speak(
            "تمام الحمد لله، مبسوط إن المشكلة اتحلت. شكراً لوقتك، مع السلامة.")]
        await _adapter.update_call_ncco(call_id, ncco)
        return await _close({"intent": "resolved", "kb_answer_given":
                             ctx.get("kb_answer_given", False),
                             "escalated": False, "transcript": tr})
    return await _transfer_to_human(ctx, call_id, tr, {
        "intent": intent, "kb_category": cat, "ticket_id": ctx.get("ticket_id", ""),
        "kb_answer_given": ctx.get("kb_answer_given", False), "transcript": tr})


async def _transfer_to_human(ctx: dict, call_id: str, tr: list, state: dict):
    """Speak the handoff line, connect a human, persist the escalation."""
    esc = await routing.escalate(state)
    ncco = [await speak("معلش على الإزعاج. أنا هحوّلك دلوقتي لممثل خدمة عملاء حقيقي يساعدك.")] + [
        {"action": "connect", "from": settings.vonage_from_number.lstrip("+") or HUMAN_AGENT_NUMBER,
         "endpoint": [{"type": "phone", "number": HUMAN_AGENT_NUMBER.lstrip("+")}]}]
    await _adapter.update_call_ncco(call_id, ncco)
    rep = await reporting.summarize({**state, "escalated": True})
    await _save(ctx.get("conv"), {**state, "escalated": True}, rep, escalation=esc)
    return {}


# ---------------------------------------------------------------------------
# Front-end SPA — keep LAST so API routes take precedence over the mounts
# ---------------------------------------------------------------------------
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def index():
    """The console UI — login screen, then role-aware dashboard."""
    return FileResponse(STATIC_DIR / "index.html")