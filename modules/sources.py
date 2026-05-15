"""External data sources: real search volume (Keywords Everywhere) and real
Amazon BSR / ratings (Keepa). Everything degrades to ``None`` on any failure so
callers fall back to mock data.

Environment variables
---------------------
    KW_EVERYWHERE_API_KEY   - Keywords Everywhere (search volume + trend)
    KEEPA_API_KEY           - Keepa (Amazon sales rank, rating, review count)

A value that is empty or still the .env placeholder ("여기에...") counts as
"not configured".
"""
from __future__ import annotations

import os
import statistics
from typing import Optional

# Per-process caches so a pipeline run hits each provider at most once per key.
_KW_CACHE: dict[tuple[str, ...], Optional[dict]] = {}
_KEEPA_CACHE: dict[str, Optional[dict]] = {}
_KEEPA_ASINS_CACHE: dict[str, Optional[list[dict]]] = {}


def _env(name: str) -> Optional[str]:
    value = os.environ.get(name, "").strip()
    if not value or value.startswith("여기에"):
        return None
    return value


def keywords_everywhere_available() -> bool:
    return _env("KW_EVERYWHERE_API_KEY") is not None


def keepa_available() -> bool:
    return _env("KEEPA_API_KEY") is not None


# --------------------------------------------------------------------------
# Keywords Everywhere — search volume + 12-month trend per keyword
# --------------------------------------------------------------------------
def keyword_volumes(terms: list[str]) -> Optional[dict[str, dict]]:
    """Return ``{term: {"vol": int, "competition": float, "trend": [int...]}}``.

    ``None`` when the API key is missing or the request fails.
    """
    key = _env("KW_EVERYWHERE_API_KEY")
    if not key or not terms:
        return None
    cache_key = tuple(sorted(terms))
    if cache_key in _KW_CACHE:
        return _KW_CACHE[cache_key]

    result: Optional[dict[str, dict]] = None
    try:
        import requests

        resp = requests.post(
            "https://api.keywordseverywhere.com/v1/get_keyword_data",
            headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
            data={"country": "us", "currency": "usd", "dataSource": "gkp", "kw[]": terms},
            timeout=25,
        )
        resp.raise_for_status()
        rows = resp.json().get("data", [])
        parsed: dict[str, dict] = {}
        for row in rows:
            term = str(row.get("keyword", "")).strip()
            if not term:
                continue
            trend = [int(t.get("value") or 0) for t in (row.get("trend") or [])]
            parsed[term] = {
                "vol": int(row.get("vol") or 0),
                "competition": float(row.get("competition") or 0.0),
                "trend": trend,
            }
        result = parsed or None
    except Exception:
        result = None

    _KW_CACHE[cache_key] = result
    return result


def trend_signal(trend_values: list[int]) -> Optional[dict]:
    """Derive growth_ratio / stability / is_seasonal from a 12-point trend."""
    pts = [v for v in trend_values if v is not None]
    if len(pts) < 4 or sum(pts) == 0:
        return None
    head = statistics.fmean(pts[: max(1, len(pts) // 4)])
    tail = statistics.fmean(pts[-max(1, len(pts) // 4):])
    growth = round(tail / head, 3) if head else 1.0
    mean = statistics.fmean(pts)
    spread = (max(pts) - min(pts)) / mean if mean else 0.0
    stdev = statistics.pstdev(pts) / mean if mean else 0.0
    return {
        "growth_ratio": max(0.3, min(3.0, growth)),
        "stability": round(max(0.0, min(1.0, 1.0 - stdev)), 3),
        "is_seasonal": spread > 0.7,
    }


# --------------------------------------------------------------------------
# Keepa — Amazon sales rank, rating, review count for a category's top products
# --------------------------------------------------------------------------
# Keepa "stats.current" CSV indices: 0 = AMAZON price, 1 = NEW price,
# 3 = SALES rank, 16 = RATING (0..50), 17 = COUNT_REVIEWS.
# See https://keepa.com/#!discuss/t/product-object/116
_IDX_AMAZON, _IDX_NEW, _IDX_SALES, _IDX_RATING, _IDX_REVIEWS = 0, 1, 3, 16, 17


def keepa_snapshot(category: str) -> Optional[dict]:
    """Best-effort real snapshot for ``category``; ``None`` on any failure.

    Returns a dict with: best_rank, median_rank, sampled_products,
    competing_listings, avg_rating, reviews_analyzed.
    """
    key = _env("KEEPA_API_KEY")
    if not key:
        return None
    if category in _KEEPA_CACHE:
        return _KEEPA_CACHE[category]

    snapshot: Optional[dict] = None
    try:  # TODO: tune parsing against live Keepa responses if fields drift.
        import keepa

        api = keepa.Keepa(key)
        cats = api.search_for_categories(category) or {}
        cat_id = next(iter(cats), None)
        if cat_id is None:
            raise RuntimeError("no matching Keepa category")

        asins = api.best_sellers_query(cat_id, domain="US") or []
        asins = list(asins)[:20]
        if not asins:
            raise RuntimeError("no best sellers returned")

        products = api.query(asins, domain="US", stats=90, rating=1, history=False) or []
        ranks: list[int] = []
        ratings: list[float] = []
        reviews: list[int] = []
        for p in products:
            cur = ((p.get("stats") or {}).get("current")) or []
            if isinstance(cur, list):
                if len(cur) > _IDX_SALES and isinstance(cur[_IDX_SALES], int) and cur[_IDX_SALES] > 0:
                    ranks.append(cur[_IDX_SALES])
                if len(cur) > _IDX_RATING and isinstance(cur[_IDX_RATING], int) and cur[_IDX_RATING] > 0:
                    ratings.append(cur[_IDX_RATING] / 10.0)
                if len(cur) > _IDX_REVIEWS and isinstance(cur[_IDX_REVIEWS], int) and cur[_IDX_REVIEWS] > 0:
                    reviews.append(cur[_IDX_REVIEWS])

        comp_listings = None
        try:
            lookup = api.category_lookup(cat_id, domain="US") or {}
            entry = lookup.get(cat_id) or next(iter(lookup.values()), {})
            comp_listings = int(entry.get("productCount") or 0) or None
        except Exception:
            comp_listings = None

        if not ranks and not ratings:
            raise RuntimeError("Keepa returned no usable rank/rating data")

        ranks_sorted = sorted(ranks)
        snapshot = {
            "best_rank": ranks_sorted[0] if ranks_sorted else None,
            "median_rank": ranks_sorted[len(ranks_sorted) // 2] if ranks_sorted else None,
            "sampled_products": len(products),
            "competing_listings": comp_listings,
            "avg_rating": round(statistics.fmean(ratings), 2) if ratings else None,
            "reviews_analyzed": int(statistics.fmean(reviews)) if reviews else None,
            "category_name": cats.get(cat_id),
        }
    except Exception:
        snapshot = None

    _KEEPA_CACHE[category] = snapshot
    return snapshot


def keepa_top_asins(category: str, n: int = 30) -> Optional[list[dict]]:
    """Top-N best-selling ASINs in ``category`` with real brand/price/reviews.

    One Keepa round-trip (~50 tokens for best_sellers_query + 1 per ASIN).
    Cached per ``(category, n)``. Returns ``None`` on any failure.
    """
    key = _env("KEEPA_API_KEY")
    if not key:
        return None
    cache_key = f"{category}::{n}"
    if cache_key in _KEEPA_ASINS_CACHE:
        return _KEEPA_ASINS_CACHE[cache_key]

    result: Optional[list[dict]] = None
    try:
        import keepa

        api = keepa.Keepa(key)
        cats = api.search_for_categories(category) or {}
        cat_id = next(iter(cats), None)
        if cat_id is None:
            raise RuntimeError("no matching Keepa category")
        asins = list(api.best_sellers_query(cat_id, domain="US") or [])[:n]
        if not asins:
            raise RuntimeError("no best sellers returned")

        products = api.query(asins, domain="US", stats=90, rating=1, history=False) or []
        out: list[dict] = []
        for p in products:
            asin = str(p.get("asin") or "").strip().upper()
            if len(asin) != 10:
                continue
            cur = ((p.get("stats") or {}).get("current")) or []

            def _cents(idx: int) -> Optional[float]:
                if len(cur) > idx and isinstance(cur[idx], int) and cur[idx] > 0:
                    return round(cur[idx] / 100.0, 2)
                return None

            price = _cents(_IDX_AMAZON) or _cents(_IDX_NEW)
            rating = None
            if len(cur) > _IDX_RATING and isinstance(cur[_IDX_RATING], int) and cur[_IDX_RATING] > 0:
                rating = round(cur[_IDX_RATING] / 10.0, 2)
            reviews = 0
            if len(cur) > _IDX_REVIEWS and isinstance(cur[_IDX_REVIEWS], int) and cur[_IDX_REVIEWS] > 0:
                reviews = int(cur[_IDX_REVIEWS])
            out.append({
                "asin": asin,
                "title": (str(p.get("title") or ""))[:120],
                "brand": str(p.get("brand") or "").strip(),
                "est_price": price,
                "rating": rating,
                "review_count": reviews,
            })
        result = out or None
    except Exception:
        result = None

    _KEEPA_ASINS_CACHE[cache_key] = result
    return result
