"""Multi-turn Arabic outbound call agent + reporting."""
import json
from datetime import datetime, timezone
from pathlib import Path

import google.generativeai as genai
import httpx
import structlog
from fastapi import FastAPI, Request
from langchain_core.messages import AIMessage, HumanMessage
from supabase import create_client

from outbound_ai.agents import intent_classifier, kb_assist, reporting, routing
from outbound_ai.config.settings import get_settings
from outbound_ai.telephony.vonage_adapter import VonageTelephonyAdapter

log = structlog.get_logger(__name__)
app = FastAPI()
settings = get_settings()
_adapter = VonageTelephonyAdapter()
CALL_STATE = {}
HUMAN_AGENT_NUMBER = "+201211497586"


def _base():
    return settings.public_webhook_base_url


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


def _save(rec):
    Path("call_reports.jsonl").open("a", encoding="utf-8").write(
        json.dumps(rec, ensure_ascii=False) + "\n")
    try:
        sb = create_client(settings.supabase_url,
                           settings.supabase_service_role_key.get_secret_value())
        sb.table("calls").insert({
            "vonage_call_id": rec.get("call_id"), "transcript": rec.get("transcript"),
            "intent": rec.get("intent"), "kb_answer": rec.get("kb_answer"),
            "kb_sources": rec.get("sources"), "kb_answer_given": rec.get("kb_answer_given"),
            "escalated": rec.get("escalated"), "escalation_reason": rec.get("escalation_reason"),
            "call_outcome": rec.get("call_outcome"), "call_summary": rec.get("call_summary"),
        }).execute()
    except Exception as e:
        log.error("supabase_save_failed", error=str(e))


@app.post("/start-call")
async def start_call(request: Request):
    b = await request.json()
    title = b.get("ticket_title", "شكوتك")
    greeting = (f"السلام عليكم، أنا المساعد الآلي من خدمة العملاء. "
                f"بكلمك بخصوص الشكوى بتاعتك عن {title}. "
                f"عايز أتطمن، المشكلة اتحلت ولا لسه؟ اتكلم بعد الصفارة.")
    ncco = [{"action": "talk", "text": greeting, "language": "ar"}, _rec(1), *_hold()]
    session, conv = await _adapter.place_call_with_ncco(
        to_number=b["phone"], from_number="12345678901", ncco=ncco)
    CALL_STATE[conv] = {"call_id": session.call_id, "ticket_id": b.get("ticket_id", ""),
                        "ticket_title": title, "category": b.get("category", "billing"),
                        "transcript": [], "turns": []}
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


@app.post("/telephony/vonage/recording")
async def recording(request: Request):
    b = await request.json()
    stage = int(request.query_params.get("stage", "1"))
    conv, url = b.get("conversation_uuid"), b.get("recording_url")
    ctx = CALL_STATE.get(conv, {})
    call_id = ctx.get("call_id")
    log.info("recording", stage=stage, call_id=call_id)
    if not url or not call_id:
        return {}

    async with httpx.AsyncClient() as c:
        audio = (await c.get(url, headers=_adapter._auth_headers(), timeout=20.0)).content
    text = _transcribe(audio)
    log.info("transcribed", stage=stage, text=text)

    tr = ctx.get("transcript", []) + [HumanMessage(content=text)]
    ctx["transcript"] = tr
    ctx.setdefault("turns", []).append(text)
    intent = await intent_classifier.classify(tr)
    log.info("intent", intent=intent)
    cat, title = ctx.get("category", "billing"), ctx.get("ticket_title", "")

    if intent == "resolved":
        await _adapter.update_call_ncco(call_id, [{"action": "talk",
            "text": "تمام الحمد لله، مبسوط إن المشكلة اتحلت. شكراً لوقتك، مع السلامة.",
            "language": "ar"}])
        rep = await reporting.summarize({"intent": intent, "kb_answer_given": True,
                                         "escalated": False, "transcript": tr})
        _save({"timestamp": datetime.now(timezone.utc).isoformat(), "call_id": call_id,
               "ticket_title": title, "transcript": " | ".join(ctx["turns"]), "intent": intent,
               "kb_answer": None, "sources": [], "kb_answer_given": False, "escalated": False,
               "call_outcome": rep["call_outcome"], "call_summary": rep["call_summary"]})
        return {}

    if stage == 1:
        ans, chunks, ok = await kb_assist.retrieve(text or title, cat)
        rep1 = await reporting.summarize({"intent": intent, "kb_answer_given": ok,
                                          "escalated": False, "transcript": tr})
        _save({"timestamp": datetime.now(timezone.utc).isoformat(), "call_id": call_id,
               "ticket_title": title, "transcript": " | ".join(ctx["turns"]), "intent": intent,
               "kb_answer": ans, "sources": [c.get("source") for c in chunks],
               "kb_answer_given": ok, "escalated": False,
               "call_outcome": rep1["call_outcome"], "call_summary": rep1["call_summary"]})
        ctx.update({"kb_answer": ans, "sources": [c.get("source") for c in chunks],
                    "kb_answer_given": ok})
        tr.append(AIMessage(content=ans))
        spoken = f"طيب، حسب المعلومات اللي عندي: {ans} جربت كده؟ المشكلة اتحلت ولا محتاج حد من الفريق يكلمك؟"
        await _adapter.update_call_ncco(call_id, [
            {"action": "talk", "text": spoken, "language": "ar"}, _rec(2), *_hold()])
        return {}

    state = {"intent": intent, "kb_category": cat, "ticket_id": ctx.get("ticket_id", ""),
             "kb_answer_given": ctx.get("kb_answer_given", False), "transcript": tr}
    esc = await routing.escalate(state)
    await _adapter.update_call_ncco(call_id, [
        {"action": "talk", "text": "معلش على الإزعاج. هحولك دلوقتي لموظف من الفريق يساعدك.",
         "language": "ar"},
        {"action": "connect", "from": "12345678901",
         "endpoint": [{"type": "phone", "number": HUMAN_AGENT_NUMBER.lstrip("+")}]}])
    rep = await reporting.summarize({**state, "escalated": True})
    _save({"timestamp": datetime.now(timezone.utc).isoformat(), "call_id": call_id,
           "ticket_title": title, "transcript": " | ".join(ctx["turns"]), "intent": intent,
           "kb_answer": ctx.get("kb_answer"), "sources": ctx.get("sources", []),
           "kb_answer_given": ctx.get("kb_answer_given", False), "escalated": True,
           "escalation_reason": esc["escalation_reason"],
           "escalation_priority": esc["escalation_priority"],
           "escalation_brief": esc["escalation_brief"],
           "call_outcome": rep["call_outcome"], "call_summary": rep["call_summary"]})
    return {}
