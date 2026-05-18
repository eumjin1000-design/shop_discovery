"""Alternative scoring weights for different operating strategies.

The default scorecard (modules.synthesizer) is calibrated for paid-ads
drop-shipping where high margin dominates. This module exposes a
re-weighting helper for the **no-ads** (organic SEO/content) strategy
where low competition matters proportionally more — 5 points are
shifted from margin (35→30) to market/competition (20→25).

Public surface
--------------
* :data:`NO_AD_WEIGHTS`     — factor → new max-score under no-ad scheme
* :func:`no_ad_score`       — recompute total for a single row
* :func:`rank_by_no_ad`     — {category_name: rank} for a list of rows
"""
from __future__ import annotations

# Re-weighted maxes — sum still 100, shifts 5 points from margin to market.
NO_AD_WEIGHTS: dict[str, int] = {
    "마진/단위 경제성": 30,        # was 35 (-5)
    "검색 트렌드": 20,             # unchanged
    "시장 및 경쟁(BSR)": 25,       # was 20 (+5)
    "리뷰 기회": 15,               # unchanged
    "구매 의도": 10,               # unchanged
}


def no_ad_score(breakdown) -> float:
    """Recompute total under no-ad weighting.

    ``breakdown`` is the [[factor_name, score, max_score], ...] list
    that :class:`modules.models.Verdict` stores. Each factor's score is
    re-scaled to its new max in :data:`NO_AD_WEIGHTS` (linearly), then
    summed. Unknown factor names pass through unchanged so the function
    is forward-compatible with new scorecard items.
    """
    total = 0.0
    for entry in breakdown or []:
        try:
            name, score, max_score = entry[0], float(entry[1]), float(entry[2])
        except (TypeError, ValueError, IndexError):
            continue
        if not max_score:
            continue
        if name in NO_AD_WEIGHTS:
            total += score * (NO_AD_WEIGHTS[name] / max_score)
        else:
            total += score
    return round(total, 1)


def rank_by_no_ad(rows: list[dict]) -> dict[str, int]:
    """Return ``{category_name: rank}`` under no-ad weighting (1 = best)."""
    scored = [(r.get("name", ""), no_ad_score(r.get("breakdown", [])))
              for r in rows]
    scored.sort(key=lambda x: x[1], reverse=True)
    return {name: i + 1 for i, (name, _s) in enumerate(scored) if name}
