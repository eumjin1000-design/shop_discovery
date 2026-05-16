"""Korea Standard Time helpers.

Streamlit Cloud runs in UTC by default, so timestamps in filenames and the
UI look wrong to a Korean user (UTC 08:56 = KST 17:56). All user-facing
times go through these helpers — fixed UTC+9 offset, no DST, no tzdata
dependency required.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


def now_kst() -> datetime:
    """KST-aware ``datetime.now()`` replacement."""
    return datetime.now(KST)


def stamp() -> str:
    """Filename-safe KST timestamp: ``20260516_175612``."""
    return now_kst().strftime("%Y%m%d_%H%M%S")


def display() -> str:
    """Human-readable KST timestamp: ``2026-05-16 17:56:12 KST``."""
    return now_kst().strftime("%Y-%m-%d %H:%M:%S KST")
