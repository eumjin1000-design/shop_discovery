"""Build a local SQLite product index from cached HuggingFace parquet shards.

Reads ``raw_meta_<Category>/full-XXXXX-of-YYYYY.parquet`` files already
downloaded by ``measure_dataset_quality.py`` (or fetches them now if absent)
and writes ``data/amazon_index.sqlite`` with the columns we need to grade
ASINs by review count per category.

Usage
-----
    python scripts/build_dataset_index.py              # 4 default categories
    python scripts/build_dataset_index.py --all        # all 9 parquet cats
    python scripts/build_dataset_index.py --categories Toys_and_Games

The script is idempotent: re-running replaces rows for the touched
categories only.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import pyarrow.parquet as pq
from huggingface_hub import hf_hub_download

REPO_ID = "McAuley-Lab/Amazon-Reviews-2023"
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "amazon_index.sqlite"

# (category, shards-in-dataset, shards-to-download). We download shard 0 only
# for big categories so the index stays small; All_Beauty is single-shard.
SHARD_PLAN = {
    "All_Beauty": (1, 1),
    "Musical_Instruments": (2, 1),
    "Toys_and_Games": (5, 1),
    "Electronics": (10, 1),
    "Handmade_Products": (1, 1),
    "Gift_Cards": (1, 1),
    "Industrial_and_Scientific": (2, 1),
    "Arts_Crafts_and_Sewing": (4, 1),
    "Cell_Phones_and_Accessories": (7, 1),
}
DEFAULT_CATEGORIES = (
    "All_Beauty", "Musical_Instruments", "Toys_and_Games", "Electronics",
)
SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    asin            TEXT PRIMARY KEY,
    category        TEXT NOT NULL,
    title           TEXT,
    brand           TEXT,
    price           REAL,
    avg_rating      REAL,
    review_count    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_cat_rc
    ON products (category, review_count DESC);
"""


def shard_path(category: str, idx: int, nshards: int) -> str:
    return f"raw_meta_{category}/full-{idx:05d}-of-{nshards:05d}.parquet"


def ingest_category(con: sqlite3.Connection, category: str) -> int:
    plan = SHARD_PLAN.get(category)
    if not plan:
        print(f"  [{category}] skipped: not in SHARD_PLAN", flush=True)
        return 0
    nshards, n_to_load = plan

    con.execute("DELETE FROM products WHERE category = ?", (category,))
    total = 0
    for i in range(n_to_load):
        rel = shard_path(category, i, nshards)
        print(f"  [{category}] shard {i+1}/{n_to_load}: {rel}", flush=True)
        local = hf_hub_download(repo_id=REPO_ID, filename=rel,
                                repo_type="dataset")
        tbl = pq.read_table(local, columns=["parent_asin", "title", "store",
                                            "price", "average_rating",
                                            "rating_number"])
        rows = []
        for r in tbl.to_pylist():
            asin = (r.get("parent_asin") or "").strip().upper()
            rc = int(r.get("rating_number") or 0)
            if len(asin) != 10 or rc <= 0:
                continue
            price = r.get("price")
            try:
                price = float(price) if price is not None else None
            except (TypeError, ValueError):
                price = None
            rows.append((
                asin, category,
                (r.get("title") or "")[:200],
                (r.get("store") or "").strip()[:80],
                price,
                r.get("average_rating"),
                rc,
            ))
        con.executemany(
            "INSERT OR REPLACE INTO products "
            "(asin, category, title, brand, price, avg_rating, review_count) "
            "VALUES (?,?,?,?,?,?,?)",
            rows,
        )
        total += len(rows)
        print(f"    inserted {len(rows):,}", flush=True)
    con.commit()
    return total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true",
                    help="ingest every parquet-format category")
    ap.add_argument("--categories", nargs="+", default=None)
    args = ap.parse_args()

    if args.all:
        cats = list(SHARD_PLAN.keys())
    else:
        cats = args.categories or list(DEFAULT_CATEGORIES)

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    grand = 0
    for c in cats:
        grand += ingest_category(con, c)
    # Summary
    print("\n=== Index Summary ===")
    cur = con.execute(
        "SELECT category, COUNT(*) AS n, MAX(review_count) "
        "FROM products GROUP BY category ORDER BY n DESC"
    )
    for cat, n, mx in cur.fetchall():
        print(f"  {cat:<35s} {n:>8,} products  (max reviews: {mx:,})")
    con.close()
    print(f"\nGrand total inserted: {grand:,}")
    print(f"SQLite: {DB_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
