"""Step 2 - search-trend signal for the category's keywords.

Uses Keywords Everywhere for real monthly search volume + 12-month trend when
``KW_EVERYWHERE_API_KEY`` is configured; otherwise deterministic mock figures
seeded from the category.

Interface
---------
    check_trend(category: str, keywords: tuple[Keyword, ...]) -> TrendResult
"""
from __future__ import annotations

from . import sources
from .models import Keyword, TrendResult
from .util import clamp, seeded_rng


def check_trend(category: str, keywords: tuple[Keyword, ...]) -> TrendResult:
    real = sources.keyword_volumes([kw.term for kw in keywords])
    if real:
        return _from_keywords_everywhere(category, keywords, real)
    return _mock(category, keywords)


def _from_keywords_everywhere(category, keywords, data) -> TrendResult:
    enriched: list[Keyword] = []
    agg_trend: list[int] = []
    for kw in keywords:
        info = data.get(kw.term, {})
        vol = int(info.get("vol") or kw.est_monthly_volume or 0)
        enriched.append(Keyword(term=kw.term, rationale=kw.rationale, est_monthly_volume=vol))
        trend = info.get("trend") or []
        for i, v in enumerate(trend):
            if i < len(agg_trend):
                agg_trend[i] += int(v or 0)
            else:
                agg_trend.append(int(v or 0))

    signal = sources.trend_signal(agg_trend) or {}
    growth = signal.get("growth_ratio", 1.0)
    stability = signal.get("stability", 0.6)
    is_seasonal = signal.get("is_seasonal", False)

    total_vol = sum(k.est_monthly_volume for k in enriched)
    direction = "rising" if growth >= 1.05 else ("declining" if growth <= 0.95 else "flat")
    notes = (
        f"Keywords Everywhere: 합산 월 검색량 ~{total_vol:,}, 12개월 추세 {direction} "
        f"({growth:.2f}x), {'계절성 있음' if is_seasonal else '연중 수요'}. [실데이터: Keywords Everywhere]"
    )
    return TrendResult(
        keywords=tuple(enriched), growth_ratio=growth, stability=stability,
        is_seasonal=is_seasonal, notes=notes,
    )


def _mock(category, keywords) -> TrendResult:
    rng = seeded_rng("trend", category)
    growth_ratio = round(rng.uniform(0.75, 1.6), 3)
    stability = round(clamp(rng.uniform(0.4, 0.95)), 3)
    is_seasonal = rng.random() < 0.3

    enriched: list[Keyword] = []
    for kw in keywords:
        if kw.est_monthly_volume > 0:
            enriched.append(kw)
            continue
        kw_rng = seeded_rng("vol", category, kw.term)
        vol = int(kw_rng.choice([320, 880, 1300, 2400, 4400, 9900, 18100]))
        enriched.append(Keyword(term=kw.term, rationale=kw.rationale, est_monthly_volume=vol))

    direction = "rising" if growth_ratio >= 1.05 else (
        "declining" if growth_ratio <= 0.95 else "flat"
    )
    notes = (
        f"12-month interest is {direction} ({growth_ratio:.2f}x); "
        f"{'seasonal peaks detected' if is_seasonal else 'demand is year-round'}. "
        "[mock data — set KW_EVERYWHERE_API_KEY for real volume]"
    )
    return TrendResult(
        keywords=tuple(enriched), growth_ratio=growth_ratio, stability=stability,
        is_seasonal=is_seasonal, notes=notes,
    )
