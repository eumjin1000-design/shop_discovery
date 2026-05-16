"""SQLite lookup over the local HuggingFace Amazon-Reviews-2023 index.

Maps a user-typed category (e.g. "wireless earbuds") to the closest dataset
category (one of ~9 ingested parquet categories) via a keyword table, then
returns the top-N ASINs by ``review_count``.

The index is built by ``scripts/build_dataset_index.py``; this module is
read-only. When the SQLite file is absent (developer never ran the build),
``top_asins`` returns ``None`` and callers degrade gracefully.

Interface
---------
    top_asins(category: str, n: int = 30) -> list[dict] | None
    db_available() -> bool
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "amazon_index.sqlite"

from .dataset_categories import CATEGORY_MAP


def db_available() -> bool:
    return DB_PATH.exists()


def map_category(user_category: str) -> Optional[str]:
    """Return the best-matching dataset category for ``user_category``."""
    text = (user_category or "").lower()
    if not text:
        return None
    for needle, cat in CATEGORY_MAP:
        if needle in text:
            return cat
    return None


def top_asins_direct(hf_category: str, n: int = 1000) -> Optional[list[dict]]:
    """Lookup by exact HF dataset category name — no keyword filter.

    Used by :mod:`modules.bulk_sourcing` when the caller already knows the
    target HF category (e.g. ``"Pet_Supplies"``) and wants raw top-N by
    review count, not a query-narrowed subset.
    """
    if not db_available():
        return None
    con = sqlite3.connect(DB_PATH)
    try:
        rows = con.execute(
            "SELECT asin, title, brand, price, avg_rating, review_count "
            "FROM products WHERE category = ? "
            "ORDER BY review_count DESC LIMIT ?",
            (hf_category, int(n)),
        ).fetchall()
    finally:
        con.close()
    if not rows:
        return None
    return [{
        "asin": r[0],
        "title": r[1] or "",
        "brand": r[2] or "",
        "est_price": float(r[3]) if r[3] is not None else None,
        "rating": float(r[4]) if r[4] is not None else None,
        "review_count": int(r[5] or 0),
        "_dataset_category": hf_category,
    } for r in rows]


def list_categories() -> list[str]:
    if not db_available():
        return []
    con = sqlite3.connect(DB_PATH)
    try:
        return [r[0] for r in con.execute(
            "SELECT DISTINCT category FROM products ORDER BY category")]
    finally:
        con.close()


_STOP_WORDS = {"the", "and", "for", "with", "from", "this", "that", "best",
               "new", "top", "set", "pack", "size", "small", "large"}


def _query_words(text: str) -> list[str]:
    """Content words 3+ chars; strip trailing 's' to match singular/plural."""
    out: list[str] = []
    for w in re.findall(r"[a-z]{3,}", text.lower()):
        if w in _STOP_WORDS:
            continue
        out.append(w[:-1] if w.endswith("s") and len(w) > 4 else w)
    seen: set[str] = set()
    return [w for w in out if not (w in seen or seen.add(w))]


def _select_with_filter(con: sqlite3.Connection, mapped: str,
                        words: list[str], n: int) -> list[tuple]:
    """Top-N rows where title matches ALL ``words`` (LIKE %word%). When the
    filtered query yields nothing, fall back to ANY-match, then to category
    only. Returns the first non-empty result tier.
    """
    base = ("SELECT asin, title, brand, price, avg_rating, review_count "
            "FROM products WHERE category = ?")
    order = " ORDER BY review_count DESC LIMIT ?"

    if words:
        likes_all = " AND " + " AND ".join("LOWER(title) LIKE ?" for _ in words)
        params = [mapped, *[f"%{w}%" for w in words], int(n)]
        rows = con.execute(base + likes_all + order, params).fetchall()
        if rows:
            return rows
        likes_any = " AND (" + " OR ".join("LOWER(title) LIKE ?"
                                           for _ in words) + ")"
        rows = con.execute(base + likes_any + order, params).fetchall()
        if rows:
            return rows
    return con.execute(base + order, (mapped, int(n))).fetchall()


def top_asins(category: str, n: int = 30) -> Optional[list[dict]]:
    """Top-N ASINs in the mapped category, narrowed by keywords from
    ``category`` (e.g. "wireless earbuds" → Electronics + title contains
    'wireless' and 'earbud'). Falls back to broader matches when the
    strictest filter is empty.

    ``None`` when the index isn't built or no category mapping matches.
    """
    if not db_available():
        return None
    mapped = map_category(category)
    if not mapped:
        return None
    words = _query_words(category)
    con = sqlite3.connect(DB_PATH)
    try:
        rows = _select_with_filter(con, mapped, words, int(n))
    finally:
        con.close()
    if not rows:
        return None
    return [{
        "asin": r[0],
        "title": r[1] or "",
        "brand": r[2] or "",
        "est_price": float(r[3]) if r[3] is not None else None,
        "rating": float(r[4]) if r[4] is not None else None,
        "review_count": int(r[5] or 0),
        "_dataset_category": mapped,
    } for r in rows]
