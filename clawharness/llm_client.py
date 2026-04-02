"""Shared LLM client factory — supports OpenRouter, Anthropic, and OpenAI.

Usage:
    from clawharness.llm_client import create_llm_client, call_llm

    client, model = create_llm_client()
    response_text = call_llm(client, model, "Generate a task config...")

Environment variables (pick ONE, checked in order):
    OPENROUTER_API_KEY — any model via OpenRouter (recommended)
    ANTHROPIC_API_KEY  — Anthropic models directly
    OPENAI_API_KEY     — OpenAI models directly

    MODEL — model name (default: claude-sonnet-4-6)
           For OpenRouter, auto-prefixed: claude-sonnet-4-6 → anthropic/claude-sonnet-4-6
"""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path


def _load_key_from_config() -> dict:
    """Try loading keys from config.json."""
    for candidate in [
        Path.cwd() / "config.json",
        Path(__file__).resolve().parent.parent / "config.json",
    ]:
        if candidate.exists():
            try:
                cfg = json.load(open(candidate))
                return {
                    "anthropic": cfg.get("claude", cfg.get("ANTHROPIC_API_KEY", "")),
                    "openai": cfg.get("OPENAI_API_KEY", ""),
                    "openrouter": cfg.get("OPENROUTER_API_KEY", ""),
                }
            except Exception:
                pass
    return {}


def detect_provider() -> tuple[str, str, str, str]:
    """Detect LLM provider from environment.

    Returns: (provider, api_key, base_url, model)
    """
    config_keys = _load_key_from_config()
    model = os.environ.get("MODEL", "claude-sonnet-4-6")

    # Priority: OpenRouter > Anthropic > OpenAI
    openrouter_key = os.environ.get("OPENROUTER_API_KEY", config_keys.get("openrouter", ""))
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", config_keys.get("anthropic", ""))
    openai_key = os.environ.get("OPENAI_API_KEY", config_keys.get("openai", ""))

    if openrouter_key:
        # OpenRouter uses OpenAI-compatible API with provider/model format
        if "/" not in model:
            model = f"anthropic/{model}"
        return "openrouter", openrouter_key, "https://openrouter.ai/api/v1", model

    if anthropic_key:
        return "anthropic", anthropic_key, "", model

    if openai_key:
        return "openai", openai_key, "https://api.openai.com/v1", model

    raise ValueError(
        "No API key found. Set OPENROUTER_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY"
    )


def call_llm(
    prompt: str,
    max_tokens: int = 4096,
    temperature: float = 0,
    provider: str = "",
    api_key: str = "",
    base_url: str = "",
    model: str = "",
) -> str:
    """Call LLM and return text response. Auto-detects provider if not specified."""
    if not provider:
        provider, api_key, base_url, model = detect_provider()

    if provider == "anthropic" and not base_url:
        return _call_anthropic(prompt, api_key, model, max_tokens, temperature)
    else:
        # OpenRouter and OpenAI both use OpenAI-compatible API
        if not base_url:
            base_url = "https://api.openai.com/v1"
        return _call_openai_compat(prompt, api_key, base_url, model, max_tokens, temperature)


def _call_anthropic(prompt: str, api_key: str, model: str, max_tokens: int, temperature: float) -> str:
    """Call Anthropic API directly."""
    body = json.dumps({
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )

    resp = urllib.request.urlopen(req, timeout=60)
    data = json.loads(resp.read())
    return data["content"][0]["text"]


def _call_openai_compat(prompt: str, api_key: str, base_url: str, model: str, max_tokens: int, temperature: float) -> str:
    """Call OpenAI-compatible API (works with OpenRouter, OpenAI, etc.)."""
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    resp = urllib.request.urlopen(req, timeout=60)
    data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]
