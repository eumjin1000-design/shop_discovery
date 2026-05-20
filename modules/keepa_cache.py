"""Disk-persistent cache for Keepa API results.

In-process caches (``sources._KEEPA_CACHE``) are lost on every Streamlit
Cloud restart, forcing repeat token spend. This JSON file cache survives
restarts, so the same category/ASIN query inside the TTL window costs
**0 tokens**.

Design notes
------------
* Only *successful* results should be stored (callers skip ``None``) — a
  no-data category is cheap to re-probe (a failed best_sellers_query is
  ~1 token) and we don't want to lock in a transient empty result.
* TTL default 24h: Keepa BSR/price move slowly enough that day-old data
  is fine for category-level scoring; product-level price checks use a
  shorter window where needed.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

_CACHE_FILE = Path(__file__).resolve().parent.parent / "keepa_data_cache.json"
DEFAULT_TTL_HOURS = 24.0


def _load() -> dict:
    try:
        with _CACHE_FILE.open(encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save(data: dict) -> None:
    try:
        with _CACHE_FILE.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
    except OSError:
        pass


def get(key: str, max_age_hours: float = DEFAULT_TTL_HOURS) -> Optional[Any]:
    """Cached value if present and younger than ``max_age_hours``, else ``None``."""
    entry = _load().get(key)
    if not isinstance(entry, dict):
        return None
    if time.time() - float(entry.get("ts", 0)) > max_age_hours * 3600:
        return None
    return entry.get("value")


def set(key: str, value: Any) -> None:  # noqa: A001 - mirror dict.set vocabulary
    """Persist ``value`` under ``key`` with the current timestamp."""
    data = _load()
    data[key] = {"ts": int(time.time()), "value": value}
    _save(data)


def stats() -> dict:
    """Cache introspection: total entries + how many are still fresh."""
    data = _load()
    now = time.time()
    fresh = sum(
        1 for e in data.values()
        if isinstance(e, dict)
        and now - float(e.get("ts", 0)) <= DEFAULT_TTL_HOURS * 3600
    )
    return {"total": len(data), "fresh": fresh, "stale": len(data) - fresh}
