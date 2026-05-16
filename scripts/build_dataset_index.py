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
import json
import os
import sqlite3
import sys
from pathlib import Path

# Redirect HuggingFace cache to D: drive (C: only has ~23GB free, Kitchen
# alone is 11GB). MUST run BEFORE huggingface_hub import.
os.environ.setdefault("HF_HOME", "D:/hf_cache")

import pyarrow.parquet as pq  # noqa: E402
from huggingface_hub import hf_hub_download  # noqa: E402

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
# jsonl-only categories ingested via raw/meta_categories/meta_<cat>.jsonl.
# Min rating_number filter keeps the SQLite small while preserving
# top-reviewed items (cheap items with 0-9 reviews are useless to us).
JSONL_PLAN = {
    "Pet_Supplies": 10,
    # 11GB jsonl, ~30M items. Aggressive min-rating filter (50) keeps SQLite
    # under ~500K rows while preserving every meaningful seller.
    "Home_and_Kitchen": 50,
    "Health_and_Household": 20,
    "Sports_and_Outdoors": 30,
    "Baby_Products": 10,
    "Office_Products": 20,
    "Beauty_and_Personal_Care": 20,
}
JSONL_TEMPLATE = "raw/meta_categories/meta_{cat}.jsonl"
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


def ingest_jsonl_category(con: sqlite3.Connection, category: str) -> int:
    """Stream the raw jsonl meta file for ``category`` line-by-line, keeping
    only items with ``rating_number >= JSONL_PLAN[category]``. Used for
    categories without parquet shards (e.g. Pet_Supplies, Home_and_Kitchen).
    """
    min_rc = JSONL_PLAN.get(category)
    if min_rc is None:
        print(f"  [{category}] skipped: not in JSONL_PLAN", flush=True)
        return 0
    rel = JSONL_TEMPLATE.format(cat=category)
    print(f"  [{category}] downloading {rel}...", flush=True)
    local = hf_hub_download(repo_id=REPO_ID, filename=rel, repo_type="dataset")
    print(f"  [{category}] streaming jsonl (min reviews={min_rc})...",
          flush=True)
    con.execute("DELETE FROM products WHERE category = ?", (category,))
    rows: list[tuple] = []
    total = 0
    scanned = 0
    with open(local, "r", encoding="utf-8") as fh:
        for line in fh:
            scanned += 1
            if scanned % 200000 == 0:
                print(f"    scanned {scanned:,}, kept {total + len(rows):,}",
                      flush=True)
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            rc = int(r.get("rating_number") or 0)
            if rc < min_rc:
                continue
            asin = (r.get("parent_asin") or "").strip().upper()
            if len(asin) != 10:
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
            if len(rows) >= 10000:
                con.executemany(
                    "INSERT OR REPLACE INTO products "
                    "(asin, category, title, brand, price, avg_rating, "
                    "review_count) VALUES (?,?,?,?,?,?,?)", rows)
                total += len(rows)
                rows = []
    if rows:
        con.executemany(
            "INSERT OR REPLACE INTO products "
            "(asin, category, title, brand, price, avg_rating, "
            "review_count) VALUES (?,?,?,?,?,?,?)", rows)
        total += len(rows)
    con.commit()
    print(f"  [{category}] scanned {scanned:,}, inserted {total:,}",
          flush=True)
    return total


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
        cats = list(SHARD_PLAN.keys()) + list(JSONL_PLAN.keys())
    else:
        cats = args.categories or list(DEFAULT_CATEGORIES)

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    grand = 0
    for c in cats:
        if c in JSONL_PLAN:
            grand += ingest_jsonl_category(con, c)
        else:
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
