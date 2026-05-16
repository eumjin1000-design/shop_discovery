"""Shared data models for the Shop Discovery pipeline.

The pipeline passes immutable dataclasses between modules. Each analysis
module consumes the previous results and returns its own result object;
``synthesizer`` aggregates everything into a single :class:`Verdict`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class DiscoveryRequest:
    """Top-level input: the category the user wants to evaluate."""

    category: str
    target_market: str = "US"
    currency: str = "USD"
    requested_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class Keyword:
    """A single search keyword derived from the category."""

    term: str
    rationale: str = ""
    # Rough monthly search volume estimate (filled by trend_check, may be 0).
    est_monthly_volume: int = 0


# --------------------------------------------------------------------------
# Per-module results
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class TrendResult:
    """Output of :mod:`modules.trend_check`."""

    keywords: tuple[Keyword, ...]
    # 12-month growth ratio, e.g. 1.25 == +25%.
    growth_ratio: float
    # 0..1, how stable the interest curve is (1 == flat/predictable).
    stability: float
    is_seasonal: bool
    notes: str = ""


@dataclass(frozen=True)
class BSRResult:
    """Output of :mod:`modules.amazon_bsr` (Amazon Best Sellers Rank)."""

    # Best (lowest) BSR seen across sampled products in the category.
    best_rank: int
    # Median BSR of sampled top products.
    median_rank: int
    sampled_products: int
    # Estimated number of competing listings (proxy for saturation).
    competing_listings: int
    notes: str = ""


@dataclass(frozen=True)
class ReviewResult:
    """Output of :mod:`modules.review_miner`."""

    reviews_analyzed: int
    avg_rating: float            # 1.0 .. 5.0
    negative_ratio: float        # share of 1-2 star reviews, 0..1
    # Recurring complaints — these are *opportunities* for a better product.
    top_complaints: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class IntentResult:
    """Output of :mod:`modules.intent_check` (commercial purchase intent)."""

    # 0..1 — fraction of keywords that read as ready-to-buy queries.
    commercial_intent: float
    # 0..1 — how problem-aware / solution-seeking the audience is.
    problem_awareness: float
    sample_queries: tuple[str, ...] = ()
    notes: str = ""
    # LLM-estimated dominant buyer age range (e.g. "25-34"); empty if not
    # estimated. Used by app/Excel to surface demographic targeting hint.
    primary_age: str = ""
    secondary_age: str = ""
    age_rationale: str = ""


@dataclass(frozen=True)
class MarginResult:
    """Output of :mod:`modules.margin_calc`."""

    avg_sourcing_cost: float     # what we pay the supplier (per unit)
    avg_retail_price: float      # what the customer pays
    shipping_cost: float
    platform_fees: float         # marketplace + payment fees
    ad_cost_estimate: float      # blended ad spend per unit (CPA proxy)
    net_margin: float            # currency amount per unit after all costs
    net_margin_pct: float        # net_margin / retail_price, 0..1
    notes: str = ""


# --------------------------------------------------------------------------
# Final verdict
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ScoreLine:
    """One row of the 100-point scorecard."""

    name: str
    score: float
    max_score: float
    detail: str = ""


@dataclass(frozen=True)
class Verdict:
    """Aggregated decision produced by :mod:`modules.synthesizer`."""

    category: str
    total_score: float           # 0 .. 100
    decision: str                # "GO" | "WATCH" | "NO-GO"
    breakdown: tuple[ScoreLine, ...]
    summary: str = ""

    GO_THRESHOLD: float = 70.0
    WATCH_THRESHOLD: float = 50.0


@dataclass(frozen=True)
class PipelineResult:
    """Everything produced by a single run — handed to the report generator."""

    request: DiscoveryRequest
    keywords: tuple[Keyword, ...]
    trend: TrendResult
    bsr: BSRResult
    review: ReviewResult
    intent: IntentResult
    margin: MarginResult
    verdict: Verdict
    finished_at: datetime = field(default_factory=datetime.now)
