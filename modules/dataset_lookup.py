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

# (keyword pattern -> HF dataset category). First match wins. Keywords are
# matched case-insensitively against the user-typed category string.
CATEGORY_MAP: list[tuple[str, str]] = [
    # All_Beauty
    ("skin", "All_Beauty"), ("beauty", "All_Beauty"), ("makeup", "All_Beauty"),
    ("hair", "All_Beauty"), ("nail", "All_Beauty"), ("cosmetic", "All_Beauty"),
    ("fragrance", "All_Beauty"), ("perfume", "All_Beauty"),
    # Electronics
    ("earbud", "Electronics"), ("headphone", "Electronics"),
    ("speaker", "Electronics"), ("camera", "Electronics"),
    ("tv", "Electronics"), ("monitor", "Electronics"), ("laptop", "Electronics"),
    ("electronic", "Electronics"), ("charger", "Electronics"),
    ("cable", "Electronics"), ("battery", "Electronics"),
    ("phone", "Electronics"), ("tablet", "Electronics"),
    # Toys_and_Games
    ("toy", "Toys_and_Games"), ("game", "Toys_and_Games"),
    ("puzzle", "Toys_and_Games"), ("doll", "Toys_and_Games"),
    ("lego", "Toys_and_Games"), ("board game", "Toys_and_Games"),
    ("children", "Toys_and_Games"), ("kids", "Toys_and_Games"),
    # Musical_Instruments
    ("guitar", "Musical_Instruments"), ("music", "Musical_Instruments"),
    ("piano", "Musical_Instruments"), ("drum", "Musical_Instruments"),
    ("microphone", "Musical_Instruments"), ("instrument", "Musical_Instruments"),
    # Industrial_and_Scientific
    ("industrial", "Industrial_and_Scientific"),
    ("scientific", "Industrial_and_Scientific"),
    ("lab", "Industrial_and_Scientific"),
    # Arts_Crafts_and_Sewing
    ("craft", "Arts_Crafts_and_Sewing"), ("sewing", "Arts_Crafts_and_Sewing"),
    ("paint", "Arts_Crafts_and_Sewing"), ("art ", "Arts_Crafts_and_Sewing"),
    # Cell_Phones_and_Accessories
    ("cell phone", "Cell_Phones_and_Accessories"),
    ("phone case", "Cell_Phones_and_Accessories"),
    ("phone accessory", "Cell_Phones_and_Accessories"),
    # Handmade_Products
    ("handmade", "Handmade_Products"), ("handcraft", "Handmade_Products"),
]


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


def list_categories() -> list[str]:
    if not db_available():
        return []
    con = sqlite3.connect(DB_PATH)
    try:
        return [r[0] for r in con.execute(
            "SELECT DISTINCT category FROM products ORDER BY category")]
    finally:
        con.close()


def top_asins(category: str, n: int = 30) -> Optional[list[dict]]:
    """Top-N ASINs in the mapped category by ``review_count``.

    ``None`` when the index isn't built or no category mapping matches.
    """
    if not db_available():
        return None
    mapped = map_category(category)
    if not mapped:
        return None
    con = sqlite3.connect(DB_PATH)
    try:
        cur = con.execute(
            "SELECT asin, title, brand, price, avg_rating, review_count "
            "FROM products WHERE category = ? "
            "ORDER BY review_count DESC LIMIT ?",
            (mapped, int(n)),
        )
        rows = cur.fetchall()
    finally:
        con.close()
    if not rows:
        return None
    out = [{
        "asin": r[0],
        "title": r[1] or "",
        "brand": r[2] or "",
        "est_price": float(r[3]) if r[3] is not None else None,
        "rating": float(r[4]) if r[4] is not None else None,
        "review_count": int(r[5] or 0),
        "_dataset_category": mapped,
    } for r in rows]
    return out
