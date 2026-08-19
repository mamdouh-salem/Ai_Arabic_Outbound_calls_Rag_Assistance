"""Shared helpers for working with the graph's transcript (a list of
LangChain BaseMessage objects, after add_messages conversion)."""
from __future__ import annotations


def transcript_to_text(transcript: list) -> str:
    lines = []
    for message in transcript:
        role = getattr(message, "type", None)
        content = getattr(message, "content", None)
        if role is None or content is None:
            continue
        speaker = "العميل" if role == "human" else "المساعد"
        lines.append(f"{speaker}: {content}")
    return "\n".join(lines)
