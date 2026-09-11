"""Regression tests for Arabic negation / resolution classification.

The failure mode being guarded against: a customer saying the problem was
NOT solved ("المشكلة ما اتحلتش") being classified as `resolved`, which
silently closes a live complaint and inflates the FCR metric.

These tests target the deterministic parts of the classifier — text
normalization, label parsing, and the regex safety net — so they run
without an LLM, without network, and without API keys.
"""
from __future__ import annotations

import pytest

from outbound_ai.agents import intent_classifier as ic


def _human(text: str) -> list:
    """Minimal transcript containing a single customer turn."""
    return [{"role": "human", "content": text}]


# --------------------------------------------------------------------------
# Normalization
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw, expected_substring",
    [
        ("المشكلة ما اتحلّتش", "اتحلتش"),   # shadda stripped
        ("المشكلـــة ما اتحلتش", "المشكله"),  # tatweel stripped
        ("إتحلت", "اتحلت"),                  # alef variants unified
        ("المشكلة", "المشكله"),               # ta marbuta -> ha
        ("لسه    مش    شغال", "لسه مش شغال"),  # whitespace collapsed
    ],
)
def test_normalization(raw: str, expected_substring: str) -> None:
    assert expected_substring in ic._normalize_arabic(raw)


# --------------------------------------------------------------------------
# Regex safety net
# --------------------------------------------------------------------------

UNRESOLVED_PHRASES = [
    "المشكلة ما اتحلتش",
    "لسه ما اتحلتش",
    "لحد دلوقتي متحلتش",
    "لأ محلتش",
    "للاسف ما اتحلّتش",
]

RESOLVED_PHRASES = [
    "أيوه اتحلت",
    "الحمد لله حليت المشكلة",
    "تمام حلت",
]


@pytest.mark.parametrize("phrase", UNRESOLVED_PHRASES)
def test_unresolved_regex_catches_negation(phrase: str) -> None:
    assert ic._UNRESOLVED_REGEX.search(ic._normalize_arabic(phrase))


@pytest.mark.parametrize("phrase", RESOLVED_PHRASES)
def test_resolved_regex_catches_confirmation(phrase: str) -> None:
    assert ic._RESOLVED_REGEX.search(ic._normalize_arabic(phrase))


# KNOWN GAP: _RESOLVED_REGEX ends with \\b, so a verb carrying an extra
# object pronoun ("حلناها" = حل+نا+ها) fails to match — the \\b lands on "ها"
# instead of a word boundary. Same for حليتها / حلتها / حلناهم. The safety net
# therefore misses these confirmations and falls back to the LLM alone.
# Suggested fix: make the trailing pronoun optional, e.g.
#   r"\\b\\w*حل(يت|ت|نا)(ها|ه|هم)?\\b"
@pytest.mark.parametrize("phrase", ["حلناها امبارح", "حليتها امبارح"])
@pytest.mark.xfail(reason="trailing object pronoun breaks the resolved regex", strict=True)
def test_resolved_regex_misses_verb_with_object_pronoun(phrase: str) -> None:
    assert ic._RESOLVED_REGEX.search(ic._normalize_arabic(phrase))


@pytest.mark.parametrize("phrase", UNRESOLVED_PHRASES)
def test_negated_phrases_never_match_resolved_regex(phrase: str) -> None:
    """The core regression: a negated phrase must not read as positive."""
    assert not ic._RESOLVED_REGEX.search(ic._normalize_arabic(phrase))


# --------------------------------------------------------------------------
# Label parsing
# --------------------------------------------------------------------------

def test_parse_intent_prefers_unresolved_over_substring_resolved() -> None:
    """'unresolved' contains 'resolved' — parsing must not pick the wrong one."""
    assert ic._parse_intent("unresolved") == "unresolved"


@pytest.mark.parametrize(
    "reply, expected",
    [
        ("resolved", "resolved"),
        ("  WANTS_HUMAN  ", "wants_human"),
        ("unclear", "unclear"),
        ("the answer is unresolved", "unresolved"),
        ("banana", "unclear"),
        ("", "unclear"),
    ],
)
def test_parse_intent(reply: str, expected: str) -> None:
    assert ic._parse_intent(reply) == expected


def test_parse_intent_priority_on_ambiguous_reply() -> None:
    """A rambling reply mentioning several labels resolves by priority,
    not by list order — the costlier mistake is ranked first."""
    assert ic._parse_intent("not resolved, so this is unresolved") == "unresolved"
    assert ic._parse_intent("unclear but wants_human") == "wants_human"


# --------------------------------------------------------------------------
# End-to-end classify() with a stubbed LLM
# --------------------------------------------------------------------------

async def test_safety_net_overrides_wrong_llm_resolved(monkeypatch) -> None:
    """If the LLM says 'resolved' but the customer clearly said it wasn't,
    the regex safety net must win."""
    monkeypatch.setattr(ic, "run_chat", lambda *a, **k: "resolved")
    assert await ic.classify(_human("لأ المشكلة ما اتحلتش")) == "unresolved"


async def test_safety_net_preserves_wants_human(monkeypatch) -> None:
    """'ماحلتش عايز أكلم حد' — escalation must survive the override."""
    monkeypatch.setattr(ic, "run_chat", lambda *a, **k: "wants_human")
    assert await ic.classify(_human("ما اتحلتش عايز أكلم حد")) == "wants_human"


async def test_safety_net_promotes_resolved(monkeypatch) -> None:
    monkeypatch.setattr(ic, "run_chat", lambda *a, **k: "unclear")
    assert await ic.classify(_human("أيوه حليت المشكلة")) == "resolved"


async def test_empty_transcript_is_unclear() -> None:
    assert await ic.classify([]) == "unclear"


async def test_no_regex_match_defers_to_llm(monkeypatch) -> None:
    """No 'حل' root present — the LLM's answer stands unmodified."""
    monkeypatch.setattr(ic, "run_chat", lambda *a, **k: "unresolved")
    assert await ic.classify(_human("النت لسه بيفصل كل شوية")) == "unresolved"
