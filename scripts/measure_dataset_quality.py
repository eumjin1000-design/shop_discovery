"""One-shot measurement: how many ASINs in HuggingFace Amazon-Reviews-2023
still resolve to a live Amazon product page in 2026.

Strategy
--------
``datasets`` v4 dropped support for the Amazon-Reviews-2023 loader script, so
we bypass it: ``huggingface_hub.hf_hub_download`` pulls the raw parquet
shards directly, then ``pyarrow`` reads them locally. For multi-shard
categories we read only the first shard (still tens of thousands of items,
enough to extract the top N by review count).

Usage
-----
    python scripts/measure_dataset_quality.py          # default 4 cats, 50 each
    python scripts/measure_dataset_quality.py --n 20   # quicker sample

Output
------
    data/measurement.json  — per-ASIN result rows
    stdout                 — survival summary table
"""
from __future__ import annotations

import argparse
import heapq
import json
import sys
import time
from pathlib import Path

import pyarrow.parquet as pq
import requests
from huggingface_hub import hf_hub_download

# 4 categories with parquet shards available. Sizes are first-shard only;
# multi-shard categories sample from shard 0.
DEFAULT_CATEGORIES = (
    "All_Beauty",            # 1 shard, ~57 MB
    "Musical_Instruments",   # 2 shards, sample shard 0 (~110 MB)
    "Toys_and_Games",        # 5 shards, sample shard 0 (~185 MB)
    "Electronics",           # 10 shards, sample shard 0 (~186 MB)
)
DEFAULT_N = 50
REPO_ID = "McAuley-Lab/Amazon-Reviews-2023"
SHARD_TEMPLATE = "raw_meta_{cat}/full-00000-of-{nshards:05d}.parquet"
# Map category -> (total shards in dataset); known from prior repo inspection.
SHARD_COUNTS = {
    "All_Beauty": 1, "Musical_Instruments": 2, "Toys_and_Games": 5,
    "Electronics": 10, "Cell_Phones_and_Accessories": 7,
    "Arts_Crafts_and_Sewing": 4, "Industrial_and_Scientific": 2,
    "Handmade_Products": 1, "Gift_Cards": 1,
}

REQ_DELAY_SEC = 0.6          # ~1.7 req/sec — well under typical bot thresholds
HEAD_TIMEOUT = 8
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "measurement.json"


def top_n_metas(category: str, n: int) -> list[dict]:
    """Download first parquet shard for ``category`` from HF and return the
    top-N items by ``rating_number``.
    """
    nshards = SHARD_COUNTS.get(category)
    if not nshards:
        print(f"  [{category}] FAIL: no known shard count")
        return []
    rel = SHARD_TEMPLATE.format(cat=category, nshards=nshards)
    print(f"  [{category}] downloading {rel}...", flush=True)
    local = hf_hub_download(repo_id=REPO_ID, filename=rel,
                            repo_type="dataset")
    print(f"  [{category}] reading parquet...", flush=True)
    tbl = pq.read_table(local, columns=["parent_asin", "title", "store",
                                        "price", "average_rating",
                                        "rating_number"])
    rows = tbl.to_pylist()
    print(f"  [{category}] {len(rows):,} rows; selecting top {n}...",
          flush=True)
    heap: list[tuple[int, str, dict]] = []
    for row in rows:
        rc = int(row.get("rating_number") or 0)
        asin = (row.get("parent_asin") or "").strip()
        if not asin or rc <= 0:
            continue
        slim = {
            "asin": asin,
            "title": (row.get("title") or "")[:120],
            "brand": (row.get("store") or "").strip(),
            "price": row.get("price"),
            "avg_rating": row.get("average_rating"),
            "review_count": rc,
        }
        if len(heap) < n:
            heapq.heappush(heap, (rc, asin, slim))
        elif rc > heap[0][0]:
            heapq.heapreplace(heap, (rc, asin, slim))
    return [item for _, _, item in sorted(heap, key=lambda t: -t[0])]


def head_check(asin: str, session: requests.Session) -> dict:
    """Amazon rejects HEAD on /dp/ with 405, so we use GET with stream=True
    and close before reading the body (only headers + status line consumed).
    """
    url = f"https://www.amazon.com/dp/{asin}"
    out: dict = {"asin": asin, "url": url}
    try:
        with session.get(url, allow_redirects=True, timeout=HEAD_TIMEOUT,
                         stream=True,
                         headers={"User-Agent": UA,
                                  "Accept-Language": "en-US",
                                  "Range": "bytes=0-2047"}) as r:
            out["status"] = r.status_code
            final = r.url or url
            out["final_url"] = final
            # Sniff a small chunk of body to detect interstitials.
            try:
                head_bytes = next(r.iter_content(2048), b"") or b""
            except Exception:
                head_bytes = b""
        body_low = head_bytes[:2048].decode("utf-8", "ignore").lower()
        is_dog_404 = "the page you requested cannot be found" in body_low or \
                     "we're sorry" in body_low and "dog" in body_low
        is_captcha = "robot check" in body_low or "captcha" in body_low or \
                     "/errors/validatecaptcha" in final.lower()

        if r.status_code == 404:
            out["verdict"] = "dead_404"
        elif is_captcha or "/errors/" in final:
            out["verdict"] = "robot_check"
        elif "/ap/signin" in final:
            out["verdict"] = "signin_wall"
        elif r.status_code in (200, 206) and "/dp/" in final and not is_dog_404:
            out["verdict"] = "live"
        elif r.status_code in (200, 206) and is_dog_404:
            out["verdict"] = "dead_dog"  # Amazon's "404" returns 200+dog page
        elif r.status_code in (301, 302, 503):
            out["verdict"] = f"redirect_{r.status_code}"
        else:
            out["verdict"] = f"other_{r.status_code}"
    except requests.RequestException as exc:
        out["status"] = -1
        out["verdict"] = "network_error"
        out["error"] = str(exc)[:200]
    return out


def measure(categories: list[str], n_per_cat: int) -> dict:
    started = time.time()
    fetch_phase: dict[str, list[dict]] = {}
    for cat in categories:
        try:
            fetch_phase[cat] = top_n_metas(cat, n_per_cat)
        except Exception as exc:
            print(f"  [{cat}] FAIL: {exc}", flush=True)
            fetch_phase[cat] = []

    print("\n=== HEAD verification ===", flush=True)
    session = requests.Session()
    results: list[dict] = []
    for cat, items in fetch_phase.items():
        print(f"  [{cat}] checking {len(items)} ASINs...", flush=True)
        for i, item in enumerate(items, 1):
            res = head_check(item["asin"], session)
            res["category"] = cat
            res["review_count"] = item["review_count"]
            results.append(res)
            if i % 10 == 0:
                live = sum(1 for r in results if r.get("category") == cat
                           and r.get("verdict") == "live")
                print(f"    {i}/{len(items)} done, live so far: {live}",
                      flush=True)
            time.sleep(REQ_DELAY_SEC)

    elapsed = time.time() - started
    return {
        "elapsed_sec": round(elapsed, 1),
        "results": results,
        "categories": categories,
        "n_per_cat": n_per_cat,
    }


def render_report(report: dict) -> str:
    rows = report["results"]
    cats = sorted({r["category"] for r in rows})
    lines: list[str] = []
    lines.append(f"\n=== Survival Report (elapsed {report['elapsed_sec']}s) ===")
    lines.append(f"{'Category':<28} {'N':>4} {'Live':>5} {'Dead':>5} "
                 f"{'Bot':>4} {'Other':>6} {'Live %':>7}")
    lines.append("-" * 66)
    grand = {"live": 0, "dead": 0, "bot": 0, "other": 0, "n": 0}
    for cat in cats:
        cat_rows = [r for r in rows if r["category"] == cat]
        live = sum(1 for r in cat_rows if r["verdict"] == "live")
        dead = sum(1 for r in cat_rows if r["verdict"] in ("dead_404", "dead_dog"))
        bot = sum(1 for r in cat_rows if r["verdict"] == "robot_check")
        other = len(cat_rows) - live - dead - bot
        pct = (100.0 * live / len(cat_rows)) if cat_rows else 0.0
        lines.append(f"{cat:<28} {len(cat_rows):>4} {live:>5} {dead:>5} "
                     f"{bot:>4} {other:>6} {pct:>6.1f}%")
        grand["live"] += live; grand["dead"] += dead
        grand["bot"] += bot; grand["other"] += other; grand["n"] += len(cat_rows)
    if grand["n"]:
        pct = 100.0 * grand["live"] / grand["n"]
        lines.append("-" * 66)
        lines.append(f"{'TOTAL':<28} {grand['n']:>4} {grand['live']:>5} "
                     f"{grand['dead']:>5} {grand['bot']:>4} {grand['other']:>6} "
                     f"{pct:>6.1f}%")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=DEFAULT_N,
                    help="ASINs per category (default 50)")
    ap.add_argument("--categories", nargs="+", default=list(DEFAULT_CATEGORIES))
    args = ap.parse_args()

    report = measure(args.categories, args.n)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(render_report(report))
    print(f"\nFull JSON: {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
