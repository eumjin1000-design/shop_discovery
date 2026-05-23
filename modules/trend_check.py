"""Step 2 - search-trend signal for the category's keywords.

Real Google search demand, in priority order:
  1. Keywords Everywhere (``KW_EVERYWHERE_API_KEY``) — real absolute volume.
  2. Google Trends via pytrends — free/keyless; real relative interest, used
     as the main signal now that Google Ads API access was abandoned.
  3. Deterministic mock seeded from the category (offline fallback).

Interface
---------
    check_trend(category: str, keywords: tuple[Keyword, ...]) -> TrendResult
"""
from __future__ import annotations

from . import sources
from .models import Keyword, TrendResult
from .util import clamp, seeded_rng


def check_trend(category: str, keywords: tuple[Keyword, ...]) -> TrendResult:
    terms = [kw.term for kw in keywords]
    real = sources.keyword_volumes(terms)
    if real:
        return _from_real(category, keywords, real, "Keywords Everywhere", abs_vol=True)
    trends = sources.google_trends(terms)
    if trends:
        return _from_real(category, keywords, trends, "Google Trends", abs_vol=False)
    return _mock(category, keywords)


def _from_real(category, keywords, data, source, abs_vol) -> TrendResult:
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
    vol_word = "합산 월 검색량" if abs_vol else "합산 관심도 추정 검색량"
    vol_note = ("[실데이터: Keywords Everywhere]" if abs_vol else
                "[실데이터: Google Trends — 검색량은 관심도(0-100) 기반 상대 추정, 순위는 구글 실데이터]")
    notes = (
        f"{source}: {vol_word} ~{total_vol:,}, 12개월 추세 {direction} "
        f"({growth:.2f}x), {'계절성 있음' if is_seasonal else '연중 수요'}. {vol_note}"
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
