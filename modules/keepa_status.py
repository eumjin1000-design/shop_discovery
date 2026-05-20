"""Keepa Pro token bucket monitor.

Polls the cheap ``/token`` endpoint (Keepa docs: free, does not consume
tokens itself) so the UI can show real-time usage. Callers should cache
the result (e.g. ``@st.cache_data(ttl=30)``) to avoid hammering Keepa on
every Streamlit rerun.

Public surface
--------------
* :func:`get_token_status`     — single JSON-ready dict for the UI.
* :func:`should_use_keepa`     — backoff guard: ``False`` when tokens
                                  are below ``min_tokens`` (default 5).
                                  Callers must check this before any
                                  paid Keepa operation.
* :func:`load_token_history`   — sliding-window history for the sidebar
                                  chart. Persisted to a gitignored JSON
                                  file under the project root.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Optional

import requests

_ENDPOINT = "https://api.keepa.com/token"
_TIMEOUT = 5.0

# Per-operation token-cost estimates (conservative upper bounds). Used by the
# UI to warn before a Keepa-consuming action. A single keepa_snapshot runs
# best_sellers_query (~1) + ~20 product fetches (~1-2 each) = ~25-50; we use
# 35 as a safe middle. Sourcing's keepa_top_asins is similar.
COST_PER_CATEGORY = 35   # single category analysis (keepa_snapshot)
COST_PER_SOURCING = 35   # sourcing list REAL_PRODUCTS block (keepa_top_asins)


def estimate_analysis_cost(n_categories: int) -> int:
    """Estimated Keepa tokens for analysing ``n_categories``."""
    return max(0, int(n_categories)) * COST_PER_CATEGORY

# History is persisted as a flat JSON list of {ts, tokensLeft, refillRate}.
# Capped at HISTORY_MAX entries (~2 hours @ 30s polling cadence).
_DATA_DIR = Path(__file__).resolve().parent.parent
_HISTORY_FILE = _DATA_DIR / "keepa_token_history.json"
HISTORY_MAX = 240


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
    status = {
        "available": True,
        "tokensLeft": tokens,
        "refillRate": rate,
        "refillIn_ms": refill_ms,
        "next_refill_secs": refill_ms // 1000,
        "color": color,
        "label": label,
        "error": None,
    }
    _append_history(status)
    return status


def should_use_keepa(min_tokens: int = 5) -> bool:
    """Backoff guard — call this BEFORE a paid Keepa operation.

    Returns ``False`` when:
      - No KEEPA_API_KEY configured
      - /token poll fails (network/HTTP error)
      - Live token balance < ``min_tokens``

    Uses an uncached poll so the decision reflects the current bucket
    (the UI's 30-second status cache is too stale for this purpose). The
    call itself is free — Keepa does not charge for /token requests.
    """
    status = get_token_status()
    if status is None or not status.get("available"):
        return False
    return int(status.get("tokensLeft", 0)) >= int(min_tokens)


def load_token_history(limit: int = HISTORY_MAX) -> list[dict[str, Any]]:
    """Return up to ``limit`` most-recent history rows (oldest → newest)."""
    try:
        with _HISTORY_FILE.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return data[-int(limit):] if limit else data


def _append_history(status: dict[str, Any]) -> None:
    rows = load_token_history(limit=HISTORY_MAX)
    rows.append({
        "ts": int(time.time()),
        "tokensLeft": int(status.get("tokensLeft", 0)),
        "refillRate": int(status.get("refillRate", 0)),
    })
    # Cap at HISTORY_MAX so the file never grows without bound.
    if len(rows) > HISTORY_MAX:
        rows = rows[-HISTORY_MAX:]
    try:
        with _HISTORY_FILE.open("w", encoding="utf-8") as fh:
            json.dump(rows, fh)
    except OSError:
        pass


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
