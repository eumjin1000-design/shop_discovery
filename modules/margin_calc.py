"""Step 6 - unit-economics / margin estimate for the category.

Margin is the make-or-break factor in dropshipping, so this module is given
the largest weight in the scorecard. Mock cost inputs for now; the structure
mirrors a real P&L so plugging in supplier/marketplace data later is trivial.

Interface
---------
    calc_margin(category, currency="USD", marketplace="amazon",
                spark_retail=None) -> MarginResult
"""
from __future__ import annotations

from typing import Optional

from .models import MarginResult
from .util import seeded_rng

# TODO: pull real sourcing prices (AliExpress/CJ) + marketplace fee schedules.

# Marketplace fee schedules. `rate` is % of retail (referral + payment),
# `flat` is a per-transaction flat fee (currency units).
PLATFORM_FEES = {
    "amazon": {"referral": 0.15, "payment": 0.0, "flat": 0.0},
    "shopify": {"referral": 0.0, "payment": 0.029, "flat": 0.30},
    "ebay": {"referral": 0.13, "payment": 0.029, "flat": 0.30},
}

# Blended ad cost as % of retail, keyed by category keyword.
AD_COST_RATES = {
    "beauty": 0.20,
    "electronics": 0.12,
    "pet": 0.15,
    "kitchen": 0.14,
    "fitness": 0.16,
    "default": 0.18,
}


def _platform_fee(retail: float, marketplace: str) -> float:
    schedule = PLATFORM_FEES.get(marketplace.lower(), PLATFORM_FEES["amazon"])
    rate = schedule["referral"] + schedule["payment"]
    return round(retail * rate + schedule["flat"], 2)


def _ad_rate_for(category: str) -> tuple[float, str]:
    lc = category.lower()
    for key, rate in AD_COST_RATES.items():
        if key == "default":
            continue
        if key in lc:
            return rate, key
    return AD_COST_RATES["default"], "default"


def calc_margin(
    category: str,
    currency: str = "USD",
    marketplace: str = "amazon",
    spark_retail: Optional[float] = None,
) -> MarginResult:
    rng = seeded_rng("margin", category)

    if spark_retail is not None and spark_retail > 0:
        retail = round(float(spark_retail), 2)
        # Reverse-engineer landed cost assuming a 2.8x markup (mid of 2.2..4).
        sourcing = round(retail / 2.8, 2)
        cost_source = "spark"
    else:
        sourcing = round(rng.uniform(3.0, 28.0), 2)
        # Dropshippers typically mark up 2.2x .. 4x over landed cost.
        markup = rng.uniform(2.2, 4.0)
        retail = round(sourcing * markup, 2)
        cost_source = "mock"

    shipping = round(rng.uniform(0.0, 6.5), 2)
    platform_fees = _platform_fee(retail, marketplace)
    ad_rate, ad_key = _ad_rate_for(category)
    ad_cost = round(retail * ad_rate, 2)

    net = round(retail - sourcing - shipping - platform_fees - ad_cost, 2)
    net_pct = round(net / retail, 3) if retail else 0.0

    if net_pct >= 0.30:
        verdict = "excellent margin"
    elif net_pct >= 0.20:
        verdict = "workable margin"
    elif net_pct >= 0.10:
        verdict = "thin margin - fragile to ad-cost swings"
    else:
        verdict = "negative/unviable margin"

    source_tag = (
        "[spark retail + reverse-engineered cost]"
        if cost_source == "spark"
        else "[mock costs]"
    )
    notes = (
        f"Per unit ({currency}, {marketplace}): retail {retail} - cost "
        f"{sourcing} - ship {shipping} - fees {platform_fees} - ads {ad_cost} "
        f"(rate {ad_rate:.0%} via '{ad_key}') = net {net} "
        f"({net_pct*100:.0f}%, {verdict}). {source_tag}"
    )
    return MarginResult(
        avg_sourcing_cost=sourcing,
        avg_retail_price=retail,
        shipping_cost=shipping,
        platform_fees=platform_fees,
        ad_cost_estimate=ad_cost,
        net_margin=net,
        net_margin_pct=net_pct,
        notes=notes,
    )
