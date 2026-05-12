"""Step 2 - search-trend signal for the category's keywords.

Real implementation would call Google Trends / Keyword Planner. Until that is
wired in, this produces deterministic mock figures seeded from the category so
runs are reproducible.

Interface
---------
    check_trend(category: str, keywords: tuple[Keyword, ...]) -> TrendResult
"""
from __future__ import annotations

from .models import Keyword, TrendResult
from .util import clamp, seeded_rng

# TODO: replace mock generation with a real Google Trends / SEO API client.


def check_trend(category: str, keywords: tuple[Keyword, ...]) -> TrendResult:
    rng = seeded_rng("trend", category)

    growth_ratio = round(rng.uniform(0.75, 1.6), 3)      # 0.75x .. 1.6x YoY
    stability = round(clamp(rng.uniform(0.4, 0.95)), 3)
    is_seasonal = rng.random() < 0.3

    # Fill in per-keyword volume estimates where the keyword generator left 0.
    enriched: list[Keyword] = []
    for kw in keywords:
        if kw.est_monthly_volume > 0:
            enriched.append(kw)
            continue
        kw_rng = seeded_rng("vol", category, kw.term)
        vol = int(kw_rng.choice([320, 880, 1300, 2400, 4400, 9900, 18100]))
        enriched.append(
            Keyword(term=kw.term, rationale=kw.rationale, est_monthly_volume=vol)
        )

    direction = "rising" if growth_ratio >= 1.05 else (
        "declining" if growth_ratio <= 0.95 else "flat"
    )
    notes = (
        f"12-month interest is {direction} ({growth_ratio:.2f}x); "
        f"{'seasonal peaks detected' if is_seasonal else 'demand is year-round'}. "
        "[mock data]"
    )
    return TrendResult(
        keywords=tuple(enriched),
        growth_ratio=growth_ratio,
        stability=stability,
        is_seasonal=is_seasonal,
        notes=notes,
    )
