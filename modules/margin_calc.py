"""Step 6 - unit-economics / margin estimate for the category.

Margin is the make-or-break factor in dropshipping, so this module is given
the largest weight in the scorecard. Mock cost inputs for now; the structure
mirrors a real P&L so plugging in supplier/marketplace data later is trivial.

Interface
---------
    calc_margin(category: str, currency: str = "USD") -> MarginResult
"""
from __future__ import annotations

from .models import MarginResult
from .util import seeded_rng

# TODO: pull real sourcing prices (AliExpress/CJ) + marketplace fee schedules.

# Marketplace + payment processing, as a fraction of retail price.
_PLATFORM_FEE_RATE = 0.15


def calc_margin(category: str, currency: str = "USD") -> MarginResult:
    rng = seeded_rng("margin", category)

    sourcing = round(rng.uniform(3.0, 28.0), 2)
    # Dropshippers typically mark up 2.2x .. 4x over landed cost.
    markup = rng.uniform(2.2, 4.0)
    retail = round(sourcing * markup, 2)
    shipping = round(rng.uniform(0.0, 6.5), 2)
    platform_fees = round(retail * _PLATFORM_FEE_RATE, 2)
    # Blended ad cost per converted unit (a big real-world margin sink).
    ad_cost = round(retail * rng.uniform(0.12, 0.45), 2)

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

    notes = (
        f"Per unit ({currency}): retail {retail} - cost {sourcing} - ship "
        f"{shipping} - fees {platform_fees} - ads {ad_cost} = net {net} "
        f"({net_pct*100:.0f}%, {verdict}). [mock costs]"
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
