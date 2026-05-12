"""Step 3 - Amazon Best Sellers Rank / competition snapshot.

Real implementation would query the Amazon Product Advertising API (or a
rank-tracking service). For now it yields deterministic mock figures.

Interface
---------
    check_bsr(category: str, keywords: tuple[Keyword, ...]) -> BSRResult
"""
from __future__ import annotations

from .models import BSRResult, Keyword
from .util import seeded_rng

# TODO: integrate Amazon PA-API / Keepa / Jungle Scout style data source.


def check_bsr(category: str, keywords: tuple[Keyword, ...]) -> BSRResult:
    rng = seeded_rng("bsr", category)

    sampled = max(10, len(keywords) * 3)
    best_rank = rng.randint(50, 6000)
    median_rank = best_rank + rng.randint(2000, 40000)
    competing_listings = rng.choice([350, 900, 1800, 4200, 9000, 21000, 48000])

    if best_rank < 1000:
        demand = "strong, proven demand"
    elif best_rank < 8000:
        demand = "healthy demand"
    else:
        demand = "thin / niche demand"

    if competing_listings < 1500:
        saturation = "low competition - room to enter"
    elif competing_listings < 10000:
        saturation = "moderate competition"
    else:
        saturation = "highly saturated - hard to differentiate"

    notes = (
        f"Top listing BSR ~{best_rank:,} ({demand}); ~{competing_listings:,} "
        f"competing listings ({saturation}). [mock data]"
    )
    return BSRResult(
        best_rank=best_rank,
        median_rank=median_rank,
        sampled_products=sampled,
        competing_listings=competing_listings,
        notes=notes,
    )
