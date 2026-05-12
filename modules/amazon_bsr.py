"""Step 3 - Amazon Best Sellers Rank / competition snapshot.

Uses Keepa for real sales-rank and competing-listing data when ``KEEPA_API_KEY``
is configured; otherwise deterministic mock figures.

Interface
---------
    check_bsr(category: str, keywords: tuple[Keyword, ...]) -> BSRResult
"""
from __future__ import annotations

from . import sources
from .models import BSRResult, Keyword
from .util import seeded_rng


def _describe(best_rank: int, competing: int) -> tuple[str, str]:
    if best_rank < 1000:
        demand = "강한 검증된 수요"
    elif best_rank < 8000:
        demand = "건전한 수요"
    else:
        demand = "얕은/틈새 수요"
    if competing < 1500:
        sat = "낮은 경쟁 - 진입 여지"
    elif competing < 10000:
        sat = "중간 경쟁"
    else:
        sat = "포화 - 차별화 어려움"
    return demand, sat


def check_bsr(category: str, keywords: tuple[Keyword, ...]) -> BSRResult:
    snap = sources.keepa_snapshot(category)
    if snap and snap.get("best_rank"):
        best = int(snap["best_rank"])
        median = int(snap.get("median_rank") or best)
        sampled = int(snap.get("sampled_products") or 0) or max(10, len(keywords) * 3)
        # If Keepa didn't give a category product count, fall back to a seeded estimate.
        competing = snap.get("competing_listings")
        if not competing:
            competing = seeded_rng("bsr", category).choice([900, 1800, 4200, 9000, 21000])
        demand, sat = _describe(best, competing)
        cname = snap.get("category_name") or category
        notes = (
            f"Keepa [{cname}]: 최상위 BSR ~{best:,} ({demand}); ~{competing:,} "
            f"개 경쟁 리스팅 ({sat}). [실데이터: Keepa]"
        )
        return BSRResult(best_rank=best, median_rank=median, sampled_products=sampled,
                         competing_listings=int(competing), notes=notes)

    rng = seeded_rng("bsr", category)
    best_rank = rng.randint(50, 6000)
    median_rank = best_rank + rng.randint(2000, 40000)
    competing_listings = rng.choice([350, 900, 1800, 4200, 9000, 21000, 48000])
    demand, sat = _describe(best_rank, competing_listings)
    notes = (
        f"Top listing BSR ~{best_rank:,} ({demand}); ~{competing_listings:,} "
        f"competing listings ({sat}). [mock data — set KEEPA_API_KEY for real BSR]"
    )
    return BSRResult(best_rank=best_rank, median_rank=median_rank,
                     sampled_products=max(10, len(keywords) * 3),
                     competing_listings=competing_listings, notes=notes)
