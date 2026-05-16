"""End-to-end production URL accuracy measurement.

Runs ``generate_sourcing_list`` for several categories (the real pipeline,
LLM included) and HEAD-checks every unique ASIN it produces. Reports the
share of rows that point at a live ``/dp/{asin}`` page.

Usage
-----
    python scripts/measure_production.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import dotenv
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
dotenv.load_dotenv()

from modules.dataset_verify import _probe  # reuse the same checker
from modules.sourcing import generate_sourcing_list

CATEGORIES = [
    ("yoga mat", False),         # Sports_and_Outdoors (new this session)
    ("hair dryer", False),       # Beauty_and_Personal_Care (new this session)
    ("dog toy", True),           # Pet_Supplies + verify_urls (circuit-breaker
                                 # validation; replaces the earlier Electronics
                                 # run that triggered IP flagging)
]


def main() -> int:
    started = time.time()
    summary: list[dict] = []
    session = requests.Session()
    for category, verify in CATEGORIES:
        t0 = time.time()
        print(f"\n=== {category!r} (verify_urls={verify}) ===", flush=True)
        res = generate_sourcing_list(category, n_subs=4, n_variants=2,
                                     verify_urls=verify)
        gen_sec = round(time.time() - t0, 1)
        unique_asins = sorted({r.asin.upper() for r in res.rows
                               if (r.asin or "").strip()})
        rows_with_dp = sum(1 for r in res.rows
                           if r.amazon_url.startswith(
                               "https://www.amazon.com/dp/"))
        print(f"  rows: {len(res.rows)}, with /dp/ URL: {rows_with_dp}, "
              f"unique ASIN: {len(unique_asins)}, generated in {gen_sec}s",
              flush=True)

        live = dead = bot = unknown = 0
        details: list[dict] = []
        for asin in unique_asins:
            status = _probe(asin, session)
            details.append({"asin": asin, "status": status})
            if status == "live": live += 1
            elif status == "dead": dead += 1
            elif status == "robot_check": bot += 1
            else: unknown += 1
            time.sleep(0.7)

        pct = (100.0 * live / len(unique_asins)) if unique_asins else 0.0
        print(f"  HEAD: live={live} dead={dead} bot={bot} unknown={unknown} "
              f"-> {pct:.1f}% live", flush=True)
        summary.append({
            "category": category, "verify_urls": verify,
            "rows": len(res.rows), "rows_with_dp": rows_with_dp,
            "unique_asins": len(unique_asins),
            "live": live, "dead": dead, "bot": bot, "unknown": unknown,
            "live_pct": round(pct, 1),
            "generated_sec": gen_sec,
            "details": details,
        })

    elapsed = round(time.time() - started, 1)
    out = Path(__file__).resolve().parent.parent / "data" / "production.json"
    out.write_text(json.dumps({"summary": summary, "elapsed_sec": elapsed},
                              indent=2), encoding="utf-8")

    print(f"\n=== Production URL Accuracy ({elapsed}s) ===")
    print(f"{'Category':<22} {'Verify':>6} {'Rows':>5} {'/dp/':>5} "
          f"{'ASIN':>5} {'Live':>5} {'Dead':>5} {'Bot':>4} {'Live%':>6}")
    print("-" * 72)
    for s in summary:
        print(f"{s['category']:<22} {str(s['verify_urls']):>6} "
              f"{s['rows']:>5} {s['rows_with_dp']:>5} "
              f"{s['unique_asins']:>5} {s['live']:>5} {s['dead']:>5} "
              f"{s['bot']:>4} {s['live_pct']:>5.1f}%")
    print(f"\nFull JSON: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
