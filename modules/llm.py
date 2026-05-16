"""LLM access with Claude-first preference + Gemini free fallback.

Tiers
-----
    "fast"     - Claude Sonnet first, Gemini Flash fallback.
                 Bulk work: category analysis, sourcing lists, generating new
                 trending categories.
    "quality"  - Claude Sonnet first, Gemini Flash fallback.
                 Creativity / nuance: shop-name ideas, Go/No-Go summary.

Both tiers currently prefer Claude because the user has paid Claude credit
they want to consume; Gemini Flash (free) acts as graceful degradation when
Claude is unavailable / rate-limited. Callers that receive ``None`` must
fall back to a deterministic heuristic.

Keys come from the environment (loaded from .env by the app):
    ANTHROPIC_API_KEY   - Claude
    GOOGLE_API_KEY      - Gemini
    GEMINI_MODEL        - optional override (default: gemini-2.0-flash)
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

_CLAUDE_MODEL = "claude-sonnet-4-6"


def _gemini_model_name() -> str:
    return os.environ.get("GEMINI_MODEL", "").strip() or "gemini-2.0-flash"


# --------------------------------------------------------------------------
# Key helpers — a value that is empty or still the .env placeholder counts as
# "not configured".
# --------------------------------------------------------------------------
def _key(name: str) -> Optional[str]:
    value = os.environ.get(name, "").strip()
    if not value or value.startswith("여기에"):
        return None
    return value


def _anthropic_key() -> Optional[str]:
    return _key("ANTHROPIC_API_KEY")


def _google_key() -> Optional[str]:
    return _key("GOOGLE_API_KEY")


# --------------------------------------------------------------------------
# Provider calls — each returns raw response text, or None on any failure.
# --------------------------------------------------------------------------
def _call_gemini(prompt: str, max_tokens: int) -> Optional[str]:
    key = _google_key()
    if key is None:
        return None
    try:
        import google.generativeai as genai

        genai.configure(api_key=key)
        model = genai.GenerativeModel(_gemini_model_name())
        resp = model.generate_content(
            prompt, generation_config={"max_output_tokens": max_tokens}
        )
        return resp.text or None
    except Exception:
        return None


def _call_claude(prompt: str, max_tokens: int) -> Optional[str]:
    key = _anthropic_key()
    if key is None:
        return None
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model=_CLAUDE_MODEL, max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text") or None
    except Exception:
        return None


_TIER_ORDER = {
    "fast": (_call_claude, _call_gemini),     # Claude first, Gemini fallback
    "quality": (_call_claude, _call_gemini),  # (was already Claude-first)
}


def _ask_raw(prompt: str, tier: str, max_tokens: int) -> Optional[str]:
    for call in _TIER_ORDER.get(tier, _TIER_ORDER["fast"]):
        text = call(prompt, max_tokens)
        if text:
            return text
    return None


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------
def any_available() -> bool:
    return bool(_anthropic_key() or _google_key())


def is_available(tier: str = "fast") -> bool:
    return any_available()  # both tiers can fall back to the other provider


def provider_label() -> str:
    g, c = _google_key() is not None, _anthropic_key() is not None
    if g and c:
        return "Claude Sonnet + Gemini Flash(폴백)"
    if c:
        return "Claude Sonnet"
    if g:
        return "Gemini Flash(무료)"
    return "없음 (mock 데이터)"


def ask_text(prompt: str, *, tier: str = "fast", max_tokens: int = 1024) -> Optional[str]:
    text = _ask_raw(prompt, tier, max_tokens)
    return text.strip() if text else None


def ask_json(prompt: str, *, tier: str = "fast", max_tokens: int = 1024) -> Optional[Any]:
    """Send ``prompt`` and parse the reply as JSON; ``None`` on any failure."""
    text = _ask_raw(prompt, tier, max_tokens)
    if not text:
        return None
    return _extract_json(text)


def _extract_json(text: str) -> Optional[Any]:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
    return None
