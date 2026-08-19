"""Gradio UI — call trigger, CSR RAG co-pilot, call reports."""
import asyncio
import json
from pathlib import Path

import gradio as gr
import pandas as pd
import requests
from supabase import create_client

from outbound_ai.agents import kb_assist
from outbound_ai.config.settings import get_settings

settings = get_settings()
API = "http://127.0.0.1:8000"
CSS = """#hdr{background:linear-gradient(90deg,#0f766e,#14b8a6);color:#fff;padding:22px;
border-radius:12px;margin-bottom:16px;text-align:center}
#hdr h1{margin:0;font-size:26px} footer{display:none!important}"""


def _sb():
    return create_client(settings.supabase_url,
                         settings.supabase_service_role_key.get_secret_value())


def load_tickets():
    try:
        rows = _sb().table("tickets").select("id,title,kb_category").eq(
            "status", "unresolved").execute().data
        return [f"{r['title']} [{r['kb_category']}] ::{r['id']}" for r in rows]
    except Exception:
        return []


def start_call(label, phone):
    if not label:
        return "اختر تذكرة أولاً."
    try:
        r = requests.post(f"{API}/start-call", json={
            "phone": phone, "ticket_title": label.split(" [")[0],
            "category": label.split("[")[1].split("]")[0],
            "ticket_id": label.split("::")[1]}, timeout=30)
        r.raise_for_status()
        return f"جاري الاتصال بـ {phone}\nCall ID: {r.json()['call_id']}"
    except Exception as e:
        return f"فشل الاتصال: {e}"


def csr_chat(message, history, category):
    try:
        ans, chunks, _ = asyncio.run(kb_assist.retrieve(message, category))
        src = "، ".join(c.get("source", "") for c in chunks) or "لا يوجد"
        return f"{ans}\n\n---\nالمصادر: {src}"
    except Exception as e:
        return f"خطأ: {e}"


def load_reports():
    p = Path("call_reports.jsonl")
    if not p.exists():
        return pd.DataFrame([{"ملاحظة": "لا توجد تقارير بعد"}])
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    rows.reverse()
    return pd.DataFrame([{
        "الوقت": r.get("timestamp", "")[:19], "التذكرة": r.get("ticket_title", ""),
        "كلام العميل": r.get("transcript", ""), "النية": r.get("intent", ""),
        "النتيجة": r.get("call_outcome", ""),
        "تم التصعيد": "نعم" if r.get("escalated") else "لا",
        "المصادر": "، ".join(filter(None, r.get("sources") or [])),
        "الملخص": r.get("call_summary", "")} for r in rows])


with gr.Blocks(theme=gr.themes.Soft(primary_hue="teal"), css=CSS) as demo:
    gr.HTML("<div id='hdr'><h1>مساعد المكالمات الصادرة بالذكاء الاصطناعي</h1>"
            "<p>متابعة التذاكر • مساعد معرفي • تقارير المكالمات</p></div>")
    with gr.Tab("بدء مكالمة"):
        t = gr.Dropdown(choices=load_tickets(), label="التذكرة المفتوحة")
        rt = gr.Button("تحديث التذاكر")
        ph = gr.Textbox(label="رقم العميل", value="+201211497586")
        b = gr.Button("ابدأ الاتصال", variant="primary")
        o = gr.Textbox(label="الحالة", lines=4)
        rt.click(lambda: gr.update(choices=load_tickets()), outputs=t)
        b.click(start_call, inputs=[t, ph], outputs=o)
    with gr.Tab("مساعد الموظف"):
        c = gr.Dropdown(["routers", "billing", "accounts"], value="billing", label="التصنيف")
        gr.ChatInterface(fn=csr_chat, additional_inputs=[c])
    with gr.Tab("تقارير المكالمات"):
        rr = gr.Button("تحديث التقارير", variant="primary")
        tbl = gr.Dataframe(value=load_reports(), wrap=True)
        rr.click(load_reports, outputs=tbl)

demo.launch(server_port=7860)
