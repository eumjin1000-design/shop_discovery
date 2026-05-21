"""Step 7 - aggregate every signal into a 100-point Go / No-Go scorecard.

Weighting (100 points total)
----------------------------
    Margin / unit economics .......... 35   (make-or-break for dropshipping)
    Search trend ..................... 20   (is demand growing & durable)
    Market & competition (BSR) ....... 20   (proven demand vs. saturation)
    Review opportunity ............... 15   (do incumbents underdeliver)
    Purchase intent .................. 10   (are searchers ready to buy)

Decision
--------
    total >= 70  -> GO
    50 <= total < 70  -> WATCH
    total < 50  -> NO-GO

Interface
---------
    synthesize(category, trend, bsr, review, intent, margin) -> Verdict
"""
from __future__ import annotations

from .models import (
    BSRResult,
    IntentResult,
    MarginResult,
    ReviewResult,
    ScoreLine,
    TrendResult,
    Verdict,
)
from .util import clamp


def synthesize(
    category: str,
    trend: TrendResult,
    bsr: BSRResult,
    review: ReviewResult,
    intent: IntentResult,
    margin: MarginResult,
) -> Verdict:
    lines = (
        _score_margin(margin),
        _score_trend(trend),
        _score_market(bsr),
        _score_review(review),
        _score_intent(intent),
    )
    total = round(sum(line.score for line in lines), 1)

    if total >= Verdict.GO_THRESHOLD:
        decision = "GO"
    elif total >= Verdict.WATCH_THRESHOLD:
        decision = "WATCH"
    else:
        decision = "NO-GO"

    summary = _summary(category, total, decision, lines)
    return Verdict(
        category=category,
        total_score=total,
        decision=decision,
        breakdown=lines,
        summary=summary,
    )


# --------------------------------------------------------------------------
# Individual scorers
# --------------------------------------------------------------------------
def _score_margin(m: MarginResult) -> ScoreLine:
    # Category reverse-calc gross margin → points (40%+ full, 20% failing).
    # Curve lives in margin_calc.margin_score so it stays with the margin domain.
    from .margin_calc import margin_score
    pts = margin_score(m.net_margin_pct)
    return ScoreLine(
        "Margin / unit economics", pts, 35.0,
        f"gross margin {m.net_margin_pct*100:.0f}% ({m.net_margin} per unit)",
    )


def _score_trend(t: TrendResult) -> ScoreLine:
    growth = clamp((t.growth_ratio - 0.8) / 0.6) * 14.0   # 0.8x..1.4x -> 0..14
    stability = t.stability * 6.0
    seasonal_penalty = 2.0 if t.is_seasonal else 0.0
    pts = round(clamp(growth + stability - seasonal_penalty, 0.0, 20.0), 1)
    return ScoreLine(
        "Search trend", pts, 20.0,
        f"{t.growth_ratio:.2f}x YoY, stability {t.stability:.2f}"
        + (", seasonal" if t.is_seasonal else ""),
    )


def _score_market(b: BSRResult) -> ScoreLine:
    if b.best_rank < 1000:
        demand = 12.0
    elif b.best_rank < 5000:
        demand = 9.0
    elif b.best_rank < 10000:
        demand = 6.0
    elif b.best_rank < 30000:
        demand = 3.0
    else:
        demand = 1.0

    if b.competing_listings < 1500:
        comp = 8.0
    elif b.competing_listings < 5000:
        comp = 6.0
    elif b.competing_listings < 10000:
        comp = 4.0
    elif b.competing_listings < 25000:
        comp = 2.0
    else:
        comp = 1.0

    pts = round(demand + comp, 1)
    return ScoreLine(
        "Market & competition (BSR)", pts, 20.0,
        f"top BSR ~{b.best_rank:,}, ~{b.competing_listings:,} competing listings",
    )


def _score_review(r: ReviewResult) -> ScoreLine:
    # Opportunity peaks around a 3.8/5 incumbent rating: low enough that buyers
    # are unhappy, high enough that the category itself works.
    opportunity = clamp(1.0 - abs(r.avg_rating - 3.8) / 1.5)
    pts = round(opportunity * 15.0, 1)
    return ScoreLine(
        "Review opportunity", pts, 15.0,
        f"incumbent avg {r.avg_rating}/5, {r.negative_ratio*100:.0f}% negative",
    )


def _score_intent(i: IntentResult) -> ScoreLine:
    pts = round(clamp(i.commercial_intent * 7.0 + i.problem_awareness * 3.0, 0.0, 10.0), 1)
    return ScoreLine(
        "Purchase intent", pts, 10.0,
        f"commercial {i.commercial_intent*100:.0f}%, "
        f"problem-aware {i.problem_awareness*100:.0f}%",
    )


def _summary(category: str, total: float, decision: str, lines) -> str:
    ranked = sorted(lines, key=lambda l: l.score / l.max_score)
    weakest = ranked[0]
    strongest = ranked[-1]
    verb = {
        "GO": "Looks worth pursuing",
        "WATCH": "Borderline - revisit with real data",
        "NO-GO": "Not worth pursuing right now",
    }[decision]
    return (
        f'{verb}: "{category}" scored {total:.0f}/100 ({decision}). '
        f"Strongest factor: {strongest.name} ({strongest.score:.0f}/"
        f"{strongest.max_score:.0f}). Weakest factor: {weakest.name} "
        f"({weakest.score:.0f}/{weakest.max_score:.0f})."
    )
