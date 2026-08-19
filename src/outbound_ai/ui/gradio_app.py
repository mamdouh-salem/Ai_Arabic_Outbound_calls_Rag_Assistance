"""Minimal Gradio demo UI — one button, places a real call.

Run: python -m outbound_ai.ui.app
Requires the FastAPI app (uvicorn ... --port 8000) and ngrok both already
running, and PUBLIC_WEBHOOK_BASE_URL in .env set to the ngrok URL.
"""
from __future__ import annotations

import asyncio

import gradio as gr

from outbound_ai.telephony.vonage_adapter import VonageTelephonyAdapter


def trigger_call(to_number: str):
    adapter = VonageTelephonyAdapter()

    async def _place():
        session = await adapter.place_call(to_number=to_number, from_number="123456789")
        return session

    session = asyncio.run(_place())
    return (
        f"تم بدء الاتصال.\n"
        f"Call ID: {session.call_id}\n"
        f"الحالة: {session.status}\n\n"
        f"(النتيجة الكاملة ستظهر في سجل خادم FastAPI بعد انتهاء المكالمة)"
    )


with gr.Blocks() as demo:
    gr.Markdown("## مساعد المكالمات الصادرة — عرض تجريبي")
    phone_input = gr.Textbox(label="رقم الهاتف (بصيغة +20...)", value="+201211497586")
    call_button = gr.Button("ابدأ الاتصال")
    output = gr.Textbox(label="النتيجة", lines=6)
    call_button.click(fn=trigger_call, inputs=phone_input, outputs=output)

if __name__ == "__main__":
    demo.launch(server_port=7860)
