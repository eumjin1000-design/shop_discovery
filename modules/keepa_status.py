"""Keepa Pro token bucket monitor.

Polls the cheap ``/token`` endpoint (Keepa docs: free, does not consume
tokens itself) so the UI can show real-time usage. Callers should cache
the result (e.g. ``@st.cache_data(ttl=30)``) to avoid hammering Keepa on
every Streamlit rerun.

Public surface
--------------
* :func:`get_token_status` — single JSON-ready dict for the UI.
"""
from __future__ import annotations

import os
from typing import Any, Optional

import requests

_ENDPOINT = "https://api.keepa.com/token"
_TIMEOUT = 5.0


def _get_key() -> Optional[str]:
    value = (os.environ.get("KEEPA_API_KEY") or "").strip()
    if not value or value.startswith("여기에"):
        return None
    return value


def get_token_status() -> Optional[dict[str, Any]]:
    """Live Keepa token state, or ``None`` when no key is configured.

    Returned dict (when key present):
        available    bool    — True on HTTP 200, False on any error
        tokensLeft   int     — current balance (can be negative)
        refillRate   int     — tokens per minute (1 on Pro plan)
        refillIn_ms  int     — ms until next +1 refill
        next_refill_secs int — convenience: refillIn_ms // 1000
        color        str     — hex CSS color for the badge
        label        str     — short Korean status word
        error        str|None — populated on failure
    """
    key = _get_key()
    if not key:
        return None
    try:
        resp = requests.get(_ENDPOINT, params={"key": key}, timeout=_TIMEOUT)
    except requests.RequestException as exc:
        return _error_payload(str(exc))
    if resp.status_code != 200:
        return _error_payload(f"HTTP {resp.status_code}")
    try:
        data = resp.json()
    except ValueError:
        return _error_payload("bad JSON")

    tokens = int(data.get("tokensLeft", 0) or 0)
    rate = int(data.get("refillRate", 0) or 0)
    refill_ms = int(data.get("refillIn", 0) or 0)

    color, label = _classify(tokens)
    return {
        "available": True,
        "tokensLeft": tokens,
        "refillRate": rate,
        "refillIn_ms": refill_ms,
        "next_refill_secs": refill_ms // 1000,
        "color": color,
        "label": label,
        "error": None,
    }


def _classify(tokens: int) -> tuple[str, str]:
    """Hex color + Korean label for the badge."""
    if tokens < 0:
        return "#c62828", "고갈"
    if tokens < 5:
        return "#c62828", "부족"
    if tokens < 30:
        return "#f9a825", "주의"
    return "#2e7d32", "양호"


def _error_payload(msg: str) -> dict[str, Any]:
    return {
        "available": False,
        "tokensLeft": 0,
        "refillRate": 0,
        "refillIn_ms": 0,
        "next_refill_secs": 0,
        "color": "#999999",
        "label": "조회 실패",
        "error": msg,
    }
