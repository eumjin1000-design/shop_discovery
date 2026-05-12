"""Thin wrapper around the Anthropic API with graceful offline fallback.

Every module that needs an LLM goes through :func:`ask_json`. If no API key
is configured (or the SDK call fails), callers receive ``None`` and are
expected to fall back to a deterministic heuristic so the pipeline still runs.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

_MODEL = "claude-sonnet-4-6"


def _client():
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    # The starter .env ships a placeholder; treat it as "not configured".
    if not key or key.startswith("여기에") or key == "여기에_API키_입력":
        return None
    try:
        import anthropic
    except ImportError:
        return None
    try:
        return anthropic.Anthropic(api_key=key)
    except Exception:
        return None


def is_available() -> bool:
    return _client() is not None


def ask_json(prompt: str, *, max_tokens: int = 1024) -> Optional[Any]:
    """Send ``prompt`` and parse the model's reply as JSON.

    Returns the parsed object, or ``None`` when the API is unavailable or the
    reply cannot be parsed. Never raises — failures degrade to ``None``.
    """
    client = _client()
    if client is None:
        return None
    try:
        msg = client.messages.create(
            model=_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(
            block.text for block in msg.content if getattr(block, "type", "") == "text"
        )
    except Exception:
        return None
    return _extract_json(text)


def _extract_json(text: str) -> Optional[Any]:
    text = text.strip()
    # Strip ```json fences if present.
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Last resort: grab the first balanced {...} or [...] block.
    match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
    return None
