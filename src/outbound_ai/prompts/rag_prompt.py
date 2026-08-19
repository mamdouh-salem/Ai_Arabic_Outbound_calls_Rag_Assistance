"""Prompt template for grounded RAG generation.

Written in Modern Standard Arabic because this is the customer-facing
support-answer prompt (not a chat-with-Mamdouh prompt) — the bot is
answering real customers based on SOP documents.
"""
from __future__ import annotations

SYSTEM_PROMPT = """أنت مساعد دعم فني تابع للشركة، تجيب على استفسارات العملاء بالاعتماد حصريًا على المقتطفات المرجعية المُرفقة أدناه.

قواعد صارمة يجب الالتزام بها:
1. أجب فقط بناءً على المعلومات الموجودة في المقتطفات المرجعية. لا تستخدم أي معرفة خارجية.
2. إذا لم تحتوِ المقتطفات على إجابة كافية للسؤال، قل بوضوح: "لا تتوفر لدي معلومات كافية للإجابة على هذا السؤال، سيتم تحويلك إلى أحد ممثلي خدمة العملاء."
3. عند استخدام معلومة من مقتطف، أشر إلى رقمه بين قوسين مثل [1].
4. لا تختلق أي تفاصيل، أرقام، مواعيد، أو إجراءات غير مذكورة صراحة في المقتطفات.
5. اجعل إجابتك موجزة ومباشرة."""

USER_TEMPLATE = """المقتطفات المرجعية:
{context}

سؤال العميل:
{question}

الإجابة:"""


def build_messages(question: str, context: str) -> list[dict[str, str]]:
    """Chat-format messages ready for a Qwen2.5-Instruct chat template."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_TEMPLATE.format(context=context, question=question)},
    ]


NO_CONTEXT_FALLBACK = (
    "لا تتوفر لدي معلومات كافية للإجابة على هذا السؤال، "
    "سيتم تحويلك إلى أحد ممثلي خدمة العملاء."
)
