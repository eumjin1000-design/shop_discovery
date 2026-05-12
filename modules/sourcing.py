"""Build a 150-item sourcing list for a GO-rated category.

Structure: 6 subcategories x 5 base products x 5 variants = 150 rows.
Each row carries an Amazon search URL, an estimated USD price, and a
high-volume / low-competition keyword. Uses Claude for the subcategory and
product ideas when available; otherwise a deterministic template fallback.

Interface
---------
    build_sourcing_list(category: str) -> list[SourcingItem]   # always len 150
"""
from __future__ import annotations

import urllib.parse
from dataclasses import dataclass

from .llm import ask_json
from .util import seeded_rng

SUBCATS_N, PRODUCTS_N, VARIANTS_N = 6, 5, 5
TOTAL = SUBCATS_N * PRODUCTS_N * VARIANTS_N  # 150
_VARIANTS = ["Standard", "Compact", "Premium", "Set of 2", "Travel Size"]


@dataclass(frozen=True)
class SourcingItem:
    subcategory: str
    base_product: str
    variant: str
    keyword: str
    est_price: float

    @property
    def product_name(self) -> str:
        return f"{self.base_product} ({self.variant})"

    @property
    def amazon_url(self) -> str:
        q = urllib.parse.quote_plus(f"{self.base_product} {self.variant}")
        return f"https://www.amazon.com/s?k={q}"


def build_sourcing_list(category: str) -> list[SourcingItem]:
    spec = _normalize(_from_llm(category), category)
    rng = seeded_rng("sourcing-price", category)
    items: list[SourcingItem] = []
    for sub in spec:
        for prod in sub["products"]:
            base = prod.get("est_price")
            keyword = (str(prod.get("keyword") or "").strip()
                       or f"best {prod['name']}".lower())
            for variant in _VARIANTS[:VARIANTS_N]:
                try:
                    price = round(float(base) * rng.uniform(0.85, 1.4), 2)
                except (TypeError, ValueError):
                    price = round(rng.uniform(7.5, 65.0), 2)
                items.append(SourcingItem(sub["subcategory"], prod["name"],
                                          variant, keyword, price))
    return items  # exactly TOTAL rows (see _normalize)


def _from_llm(category: str) -> list[dict] | None:
    prompt = (
        f'For a dropshipping store in the "{category}" niche, propose '
        f"{SUBCATS_N} subcategories. For each subcategory list {PRODUCTS_N} "
        "specific product ideas; for each product give a high-search-volume, "
        "low-competition keyword and a rough USD retail price estimate. Return "
        'ONLY a JSON array: [{"subcategory": "...", "products": [{"name": "...", '
        '"keyword": "...", "est_price": <number>}, ...]}, ...]. No prose.'
    )
    data = ask_json(prompt, max_tokens=3000)
    if not isinstance(data, list):
        return None
    clean: list[dict] = []
    for sub in data:
        if not isinstance(sub, dict):
            continue
        prods = [p for p in sub.get("products", [])
                 if isinstance(p, dict) and str(p.get("name", "")).strip()]
        if str(sub.get("subcategory", "")).strip() and prods:
            clean.append({"subcategory": str(sub["subcategory"]).strip(),
                          "products": prods})
    return clean or None


def _fallback_spec(category: str) -> list[dict]:
    subs = [f"Compact {category}", f"Premium {category}", f"{category} Accessories",
            f"Portable {category}", f"{category} for Travel", f"{category} Gift Sets"]
    return [
        {"subcategory": s,
         "products": [{"name": f"{s} Model {j}",
                       "keyword": f"{s.lower()} {j}", "est_price": None}
                      for j in range(1, PRODUCTS_N + 1)]}
        for s in subs
    ]


def _normalize(spec: list[dict] | None, category: str) -> list[dict]:
    """Coerce ``spec`` to exactly SUBCATS_N x PRODUCTS_N, padding from fallback."""
    fb = _fallback_spec(category)
    spec = list(spec or fb)[:SUBCATS_N]
    while len(spec) < SUBCATS_N:
        spec.append(fb[len(spec)])
    for sub in spec:
        prods = list(sub.get("products", []))[:PRODUCTS_N]
        while len(prods) < PRODUCTS_N:
            prods.append({"name": f"{sub['subcategory']} Item {len(prods) + 1}",
                          "keyword": None, "est_price": None})
        sub["products"] = prods
    return spec
