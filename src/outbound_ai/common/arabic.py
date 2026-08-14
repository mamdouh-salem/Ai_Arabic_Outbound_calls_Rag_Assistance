"""Arabic text normalization.

Shared by the voice layer (normalizing STT output before intent classification) and the
RAG layer (normalizing both KB chunks and queries before sparse/full-text matching).

Normalization is for *matching only*. The raw text is always preserved alongside it —
transcripts, reports and citations must show what was actually said or written.
"""

from __future__ import annotations

import re
import unicodedata

# Tashkeel (harakat), tanween, shadda, sukun, superscript alef.
_DIACRITICS = re.compile(r"[ً-ٰٟۖ-ۭ]")
# Tatweel / kashida: نعـــم -> نعم
_TATWEEL = re.compile(r"ـ")
_WHITESPACE = re.compile(r"\s+")

# Arabic-Indic (٠-٩) and Extended Arabic-Indic (۰-۹) digits -> ASCII
_DIGIT_MAP = {ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")}
_DIGIT_MAP.update({ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")})

_LETTER_MAP = {
    # Alef variants -> bare alef
    "أ": "ا",  # أ
    "إ": "ا",  # إ
    "آ": "ا",  # آ
    "ٱ": "ا",  # ٱ
    # Alef maqsura -> ya  (مصطفى ≡ مصطفي)
    "ى": "ي",
    # Ta marbuta -> ha    (مشكلة ≡ مشكله)
    "ة": "ه",
    # Hamza carriers
    "ؤ": "و",  # ؤ -> و
    "ئ": "ي",  # ئ -> ي
    # Arabic punctuation -> ASCII, so sentence splitting has one rule set
    "،": ",",  # ،
    "؛": ";",  # ؛
    "؟": "?",  # ؟
}
_LETTER_TRANS = str.maketrans(_LETTER_MAP)


def strip_diacritics(text: str) -> str:
    """Remove tashkeel and tatweel. Safe to use on text shown to humans."""
    return _TATWEEL.sub("", _DIACRITICS.sub("", text))


def normalize_digits(text: str) -> str:
    """Arabic-Indic digits to ASCII, so `تذكرة رقم ١٢٣` matches ticket 123."""
    return text.translate(_DIGIT_MAP)


def normalize_arabic(text: str) -> str:
    """Aggressive normalization for matching and classification.

    Lossy by design: alef forms, ta marbuta and alef maqsura are collapsed, which is
    exactly what makes `مشكلة` match `مشكله` in sparse retrieval and what makes the
    intent classifier see one spelling of `أيوة / ايوه`.

    Never store the result as the transcript — store it beside `text_raw`.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = strip_diacritics(text)
    text = normalize_digits(text)
    text = text.translate(_LETTER_TRANS)
    return _WHITESPACE.sub(" ", text).strip()


def normalize_light(text: str) -> str:
    """Cosmetic cleanup only: NFKC, diacritics, tatweel, whitespace.

    Letter forms are preserved, so the result is still correct Arabic to display or to
    send to TTS. Use this for text a human or a voice will consume.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = strip_diacritics(text)
    return _WHITESPACE.sub(" ", text).strip()


def contains_arabic(text: str) -> bool:
    """True if the string holds at least one Arabic-script character."""
    return any("؀" <= ch <= "ۿ" or "ݐ" <= ch <= "ݿ" for ch in text)
