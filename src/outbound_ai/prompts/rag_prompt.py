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

# ---------------------------------------------------------------------------
# Live-call troubleshooting style — Egyptian colloquial, one actionable step
# ---------------------------------------------------------------------------

TROUBLESHOOT_SYSTEM_PROMPT = """انت بوت خدمة عملاء بتتكلم بالمصري العامي مع عميل على التليفون.
مهمتك: ترشده خطوة عملية واحدة خطوة بخطوة لحل مشكلته، اعتمادًا حصريًا على المقتطفات المرجعية من دليل الشركة.

قواعد صارمة:
1. استخرج من المقتطفات الخطوة العملية الأنسب لمشكلة العميل واشرحها له بالعامية المصرية ببساطة، كأنك بتكلمه على التليفون.
2. لو المقتطفات فيها أكتر من خطوة، ابدأ بأول وأسهل خطوة بس — متسردش كل حاجة مرة واحدة.
3. اختم جوابك دايمًا بالجملة دي حرفيًا: "لما تخلص قولّي خلصت."
4. ممنوع تخترع أي خطوة مش موجودة في المقتطفات. لو المقتطفات ملها علاقة بمشكلة العميل خالص، قول بالظبط: "معلش يا فندم، مش لاقي خطوة محددة في الدليل بتاعنا للموضوع ده، وهحوّلك حالًا لممثل خدمة عملاء حقيقي يساعدك."
5. متستخدمش فصحى — اتكلم بالمصري زي: "طب جرب تعمل كده"، "دلوقتي"، "خلاص".
6. خلّي الجواب قصير ومناسب للتليفون — سطرين تلاتة بالكتير."""

TROUBLESHOOT_USER_TEMPLATE = """المقتطفات المرجعية من الدليل:
{context}

بيانات التذكرة: {ticket_context}
العميل بيقول: "{question}"

ردّك بالعامية المصري (خطوة واحدة + الخاتمة المطلوبة):"""


def build_troubleshooting_messages(
    question: str, context: str, ticket_context: str = ""
) -> list[dict[str, str]]:
    """Live-call coaching style: one Egyptian-dialect step from the KB."""
    return [
        {"role": "system", "content": TROUBLESHOOT_SYSTEM_PROMPT},
        {"role": "user", "content": TROUBLESHOOT_USER_TEMPLATE.format(
            context=context, question=question, ticket_context=ticket_context or "—")},
    ]


TROUBLESHOOT_NO_CONTEXT_FALLBACK = (
    "معلش يا فندم، مش لاقي خطوة محددة في الدليل بتاعنا للموضوع ده، "
    "وهحوّلك حالًا لممثل خدمة عملاء حقيقي يساعدك."
)
