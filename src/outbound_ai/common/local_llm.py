"""Shared LLM access — local Qwen2.5-7B-Instruct (4-bit) or a hosted OpenAI
model, chosen via settings.generation_provider.

Local, 4-bit quantized. Loaded exactly once per process via lru_cache. Every
caller that needs the local generation model MUST go through get_local_llm()
rather than loading its own copy — a 4-bit-quantized 7B model already uses
~5.5GB VRAM (the budget this was originally sized for: a 6GB card with room
left for the embedding model + OS overhead), so a second independent load
would very likely OOM.

KNOWN LIMITATION: HF's model.generate() isn't guaranteed safe for truly
concurrent calls from multiple threads sharing one model instance. Right now
kb_assist and intent_classifier both route through this via asyncio.to_thread,
so two calls could overlap under real concurrent traffic (multiple live
calls at once). Fine for now / single-call testing; revisit with a request
queue or a dedicated inference server (vLLM, TGI) before real concurrent load.

run_chat() is the one function every caller (rag/generation.py,
agents/intent_classifier.py) should use — it hides which provider is
actually running behind settings.generation_provider, so nothing upstream
needs to change when you switch between local and openai.
"""
from __future__ import annotations

from functools import lru_cache

import structlog

from outbound_ai.config.settings import get_settings

log = structlog.get_logger(__name__)


@lru_cache(maxsize=1)
def get_local_llm():
    """Returns (tokenizer, model), loaded once and cached for the process
    lifetime. Only called when generation_provider == "local" — importing
    torch/transformers/bitsandbytes is deferred inside this function so the
    OpenAI path never pays that import cost or needs those packages ready.
    """
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    settings = get_settings()
    quant_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_quant_type="nf4",
    )
    log.info("loading_local_llm", model=settings.local_generation_model)
    tokenizer = AutoTokenizer.from_pretrained(settings.local_generation_model)
    model = AutoModelForCausalLM.from_pretrained(
        settings.local_generation_model,
        quantization_config=quant_config,
        device_map=settings.generation_device,
    )
    return tokenizer, model


def _run_chat_local(messages: list[dict], *, max_new_tokens: int, temperature: float) -> str:
    import torch

    tokenizer, model = get_local_llm()
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            do_sample=temperature > 0,
        )
    generated = output_ids[0][inputs["input_ids"].shape[1] :]
    return tokenizer.decode(generated, skip_special_tokens=True).strip()


@lru_cache(maxsize=1)
def _get_openai_client():
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    return ChatOpenAI(
        model=settings.openai_call_model,
        api_key=settings.openai_api_key,
    )


def _run_chat_openai(messages: list[dict], *, max_new_tokens: int, temperature: float) -> str:
    client = _get_openai_client()
    response = client.invoke(
        messages,
        max_tokens=max_new_tokens,
        temperature=temperature,
    )
    return response.content.strip()


@lru_cache(maxsize=8)
def _get_gemini_client(max_new_tokens: int = 512, temperature: float = 0.2):
    from langchain_google_genai import ChatGoogleGenerativeAI

    settings = get_settings()
    api_key = settings.gemini_api_key.get_secret_value() if settings.gemini_api_key else None
    return ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        api_key=api_key,
        # Gemini 3+ defaults to thinking_level="high" if unset, which burns
        # part of max_output_tokens on internal reasoning before the visible
        # answer — that's what was truncating responses. "low" is also just
        # the right choice for a latency-critical in-call agent regardless.
        thinking_level="low",
        # Bind sampling params at CONSTRUCTION time: recent langchain-google-
        # genai builds reject any per-invoke kwarg (version skew with the
        # underlying GenerativeServiceClient signature).
        max_output_tokens=max_new_tokens,
        temperature=temperature,
    )


def _extract_text(content) -> str:
    """Gemini 3.x's LangChain integration returns response.content as a list
    of content blocks (text/other parts), not a plain string like
    ChatOpenAI's .content — this normalizes either shape to plain text."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(item.get("text") or item.get("content") or "")
        return "".join(parts).strip()
    return str(content).strip()


def _run_chat_gemini(messages: list[dict], *, max_new_tokens: int, temperature: float) -> str:
    client = _get_gemini_client(max_new_tokens=max_new_tokens, temperature=temperature)
    response = client.invoke(messages)
    return _extract_text(response.content)


def run_chat(messages: list[dict], *, max_new_tokens: int, temperature: float) -> str:
    """One chat completion call, routed to local, OpenAI, or Gemini per
    settings.generation_provider.

    Blocking either way (local is GPU-bound, both APIs are network calls) —
    async callers must run this via asyncio.to_thread rather than awaiting
    it directly, or it stalls the event loop while it runs.
    """
    settings = get_settings()
    if settings.generation_provider == "openai":
        return _run_chat_openai(messages, max_new_tokens=max_new_tokens, temperature=temperature)
    if settings.generation_provider == "gemini":
        return _run_chat_gemini(messages, max_new_tokens=max_new_tokens, temperature=temperature)
    return _run_chat_local(messages, max_new_tokens=max_new_tokens, temperature=temperature)
