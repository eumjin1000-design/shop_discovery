"""Step 6 - unit-economics / margin estimate (category reverse-calculation).

Replaces the old random-mock cost model with a real formula:

    gross_margin  = amazon_avg_price - sourcing_cost - intl_shipping
    sourcing_cost = amazon_avg_price * SOURCING_RATE (0.25)
    intl_shipping = category-based tier (volumetric-weight proxy)

This is a **gross sourcing margin** (before marketplace fees & ad spend).
It answers "is there enough headroom to source this category profitably?"
— the make-or-break dropshipping signal, hence the 35-point scorecard
weight. Marketplace fees / ad cost are channel- and strategy-specific, so
they are layered downstream rather than baked into this estimate.

Interface
---------
    calc_margin(category, currency="USD", amazon_avg_price=None,
                marketplace="amazon", spark_retail=None) -> MarginResult
    margin_score(net_margin_pct) -> float   # 0..35 scorecard points
"""
from __future__ import annotations

from typing import Optional

from .models import MarginResult
from .util import seeded_rng

# Landed sourcing cost as a fraction of the Amazon retail price. 0.25 = a
# product retailing at $40 on Amazon costs ~$10 to source/land.
SOURCING_RATE = 0.25

# International shipping tiers (USD/unit) keyed by volumetric weight. Bulky
# items are dominated by dimensional-weight freight (eats margin); small
# light items ship cheap. Matched on keywords in the category/keyword text.
SHIPPING_TIERS = {
    "heavy": (12.0, 15.0),
    "light": (3.0, 5.0),
    "standard": (7.0, 8.0),
}
_HEAVY_WORDS = {
    "pillow", "bed", "mattress", "ramp", "furniture", "rug", "cushion",
    "blanket", "sofa", "chair", "table", "crate", "tent", "kayak", "frame",
    "mirror", "lamp", "stroller", "seat", "wedge", "bolster", "mat", "desk",
    "shelf", "cabinet", "organizer", "bin", "backpack", "luggage", "board",
}
_LIGHT_WORDS = {
    "collar", "leash", "tag", "sticker", "patch", "ring", "necklace",
    "bracelet", "earring", "cable", "charger", "strap", "band", "sock",
    "glove", "mask", "bookmark", "keychain", "clip", "pin", "cover",
    "case", "insole", "brush", "comb", "spoon", "stylus",
}


def _shipping_for(category: str, rng) -> tuple[float, str]:
    """Pick the shipping tier from category/keyword text; cost is seeded so a
    given category always maps to the same value (reproducible)."""
    words = set(category.lower().split())
    if words & _HEAVY_WORDS or any(w in category.lower() for w in _HEAVY_WORDS):
        tier = "heavy"
    elif words & _LIGHT_WORDS or any(w in category.lower() for w in _LIGHT_WORDS):
        tier = "light"
    else:
        tier = "standard"
    lo, hi = SHIPPING_TIERS[tier]
    return round(rng.uniform(lo, hi), 2), tier


def margin_score(net_margin_pct: float) -> float:
    """Gross-margin fraction (0..1) → 0..35 scorecard points.

    40%+ → full 35 · 20% → 10 (과락/failing line) · linear between ·
    below 20% → linear down to 0 (heavily penalised) · <=0% → 0.
    """
    pct = float(net_margin_pct)
    if pct >= 0.40:
        return 35.0
    if pct <= 0.0:
        return 0.0
    if pct >= 0.20:
        # workable zone: 20% -> 10, 40% -> 35
        return round(10.0 + (pct - 0.20) / 0.20 * 25.0, 1)
    # failing zone: 0% -> 0, 20% -> 10
    return round(pct / 0.20 * 10.0, 1)


def calc_margin(
    category: str,
    currency: str = "USD",
    amazon_avg_price: Optional[float] = None,
    marketplace: str = "amazon",
    spark_retail: Optional[float] = None,
) -> MarginResult:
    rng = seeded_rng("margin", category)

    # Retail = Amazon 1st-page average price. Real value when provided
    # (amazon_avg_price preferred, then spark_retail); otherwise a
    # category-seeded estimate so the pipeline still produces a number.
    if amazon_avg_price is not None and amazon_avg_price > 0:
        retail = round(float(amazon_avg_price), 2)
        price_src = "amazon avg"
    elif spark_retail is not None and spark_retail > 0:
        retail = round(float(spark_retail), 2)
        price_src = "spark retail"
    else:
        retail = round(rng.uniform(15.0, 55.0), 2)
        price_src = "estimate"

    sourcing = round(retail * SOURCING_RATE, 2)
    shipping, ship_tier = _shipping_for(category, rng)

    # Gross sourcing margin: retail - sourcing - intl shipping.
    net = round(retail - sourcing - shipping, 2)
    net_pct = round(net / retail, 3) if retail else 0.0

    if net_pct >= 0.40:
        verdict = "excellent margin"
    elif net_pct >= 0.20:
        verdict = "workable margin"
    elif net_pct > 0:
        verdict = "thin/failing margin"
    else:
        verdict = "negative/unviable margin"

    notes = (
        f"Per unit ({currency}): Amazon avg {retail} [{price_src}] - sourcing "
        f"{sourcing} (25%) - intl ship {shipping} ({ship_tier} tier) = gross "
        f"margin {net} ({net_pct*100:.0f}%, {verdict}). 마켓수수료·광고비 별도 차감."
    )
    return MarginResult(
        avg_sourcing_cost=sourcing,
        avg_retail_price=retail,
        shipping_cost=shipping,
        platform_fees=0.0,      # channel-specific; layered downstream
        ad_cost_estimate=0.0,   # strategy-specific; layered downstream
        net_margin=net,
        net_margin_pct=net_pct,
        notes=notes,
    )
