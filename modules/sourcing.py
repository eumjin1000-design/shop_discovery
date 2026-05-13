"""Build a sourcing list for a GO-rated category.

Sized ``n_subs × PRODUCTS_N × n_variants`` (default 6 × 5 × 5 = 150). Each row
carries: subcategory, base product, variant, an estimated incumbent brand, a
high-search-volume / low-competition keyword, an estimated USD price, an Amazon
**browse-node** search URL (Prime-eligible, sorted by review count — what a
scraper such as Spark crawls to expand into real ASINs per subcategory), plus
``asin`` / ``review_count`` placeholder fields the scraper fills in later.

Subcategory + product ideas come from Claude/Gemini when available; otherwise a
deterministic template fallback. Prices use a category-seeded RNG so a given
category always yields the same numbers.

Interface
---------
    generate_sourcing_list(category, n_subs=6, n_variants=5) -> SourcingResult
"""
from __future__ import annotations

import urllib.parse
from dataclasses import dataclass

from .llm import ask_json
from .util import seeded_rng

PRODUCTS_N = 5                 # products per subcategory (fixed)
DEFAULT_SUBS = 6
DEFAULT_VARIANTS = 5
_VARIANT_POOL = ["Standard", "Compact", "Premium", "Set of 2", "Travel Size",
                 "Mini", "XL", "Refill Pack", "Gift Box", "Pro"]
_PRIME_NODE_US = "23533298011"  # p_n_prime_eligibility filter id on amazon.com


@dataclass(frozen=True)
class SourcingRow:
    subcategory: str
    base_product: str
    variant: str
    brand: str
    keyword: str
    est_price: float
    amazon_node_id: str = ""
    asin: str = ""              # filled by the scraper (Spark)
    review_count: int = 0       # filled by the scraper

    @property
    def product_name(self) -> str:
        return f"{self.base_product} ({self.variant})"

    @property
    def amazon_url(self) -> str:
        """Browse-node search, Prime-eligible, sorted by review count.

        Falls back to a keyword search when no browse-node id is available.
        """
        if self.amazon_node_id:
            rh = (f"n%3A{urllib.parse.quote(str(self.amazon_node_id))}"
                  f"%2Cp_n_prime_eligibility%3A{_PRIME_NODE_US}")
            return f"https://www.amazon.com/s?rh={rh}&s=review-count-rank"
        q = urllib.parse.quote_plus(f"{self.base_product} {self.variant}")
        return f"https://www.amazon.com/s?k={q}&s=review-count-rank"


@dataclass(frozen=True)
class SourcingResult:
    category: str
    rows: tuple[SourcingRow, ...]
    n_subs: int
    n_variants: int
    total: int
    summary: str


def generate_sourcing_list(category: str, n_subs: int = DEFAULT_SUBS,
                           n_variants: int = DEFAULT_VARIANTS) -> SourcingResult:
    n_subs = max(1, int(n_subs))
    n_variants = max(1, min(len(_VARIANT_POOL), int(n_variants)))
    spec = _normalize(_from_llm(category, n_subs), category, n_subs)
    variants = _VARIANT_POOL[:n_variants]
    rng = seeded_rng("sourcing-price", category)

    rows: list[SourcingRow] = []
    for sub in spec:
        node_id = str(sub.get("amazon_node_id") or "").strip()
        for prod in sub["products"]:
            base = prod.get("est_price")
            keyword = (str(prod.get("keyword") or "").strip()
                       or f"best {prod['name']}".lower())
            brand = str(prod.get("brand") or "").strip()
            asin = str(prod.get("asin") or "").strip()
            try:
                rc = max(0, int(prod.get("review_count") or 0))
            except (TypeError, ValueError):
                rc = 0
            for variant in variants:
                try:
                    price = round(float(base) * rng.uniform(0.85, 1.4), 2)
                except (TypeError, ValueError):
                    price = round(rng.uniform(7.5, 65.0), 2)
                rows.append(SourcingRow(
                    subcategory=sub["subcategory"], base_product=prod["name"],
                    variant=variant, brand=brand, keyword=keyword, est_price=price,
                    amazon_node_id=node_id, asin=asin, review_count=rc,
                ))

    total = len(rows)
    summary = (
        f"{category} 소싱 리스트 — {n_subs}개 서브카테고리 × {PRODUCTS_N}개 상품 "
        f"× {n_variants}개 변형 = {total}개. Amazon URL은 브라우즈 노드 + Prime + "
        "리뷰순(스크래퍼 수집용); brand는 추정, asin/review_count는 스크래퍼가 채울 플레이스홀더."
    )
    return SourcingResult(category=category, rows=tuple(rows), n_subs=n_subs,
                          n_variants=n_variants, total=total, summary=summary)


def _from_llm(category: str, n_subs: int) -> list[dict] | None:
    prompt = (
        f'For a dropshipping store in the "{category}" niche, propose {n_subs} '
        "subcategories. For each subcategory give its Amazon US browse-node id "
        '("amazon_node_id" — numeric string if you know it, else "") and list '
        f'{PRODUCTS_N} specific product ideas; for each product give a likely '
        'incumbent "brand", a high-search-volume low-competition "keyword", a '
        'rough USD retail price "est_price", and if known an "asin" and '
        '"review_count" (else "" and 0). Return ONLY a JSON array: '
        '[{"subcategory": "...", "amazon_node_id": "...", "products": [{"name": '
        '"...", "brand": "...", "keyword": "...", "est_price": <num>, "asin": '
        '"...", "review_count": <int>}, ...]}, ...]. No prose.'
    )
    data = ask_json(prompt, max_tokens=3500)
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
                          "amazon_node_id": sub.get("amazon_node_id", ""),
                          "products": prods})
    return clean or None


def _fallback_spec(category: str, n_subs: int) -> list[dict]:
    base = [f"Compact {category}", f"Premium {category}", f"{category} Accessories",
            f"Portable {category}", f"{category} for Travel", f"{category} Gift Sets",
            f"{category} Bundles", f"{category} Essentials", f"Smart {category}",
            f"{category} Refills"]
    out: list[dict] = []
    for i in range(n_subs):
        name = base[i % len(base)]
        if i >= len(base):
            name = f"{name} #{i // len(base) + 1}"
        out.append({
            "subcategory": name, "amazon_node_id": "",
            "products": [{"name": f"{name} Model {j}", "brand": "",
                          "keyword": f"{name.lower()} {j}", "est_price": None,
                          "asin": "", "review_count": 0}
                         for j in range(1, PRODUCTS_N + 1)],
        })
    return out


def _normalize(spec: list[dict] | None, category: str, n_subs: int) -> list[dict]:
    """Coerce ``spec`` to exactly ``n_subs`` subcategories × PRODUCTS_N products."""
    fb = _fallback_spec(category, n_subs)
    spec = list(spec or fb)[:n_subs]
    while len(spec) < n_subs:
        spec.append(fb[len(spec)])
    for sub in spec:
        sub.setdefault("amazon_node_id", "")
        prods = list(sub.get("products", []))[:PRODUCTS_N]
        while len(prods) < PRODUCTS_N:
            prods.append({"name": f"{sub['subcategory']} Item {len(prods) + 1}",
                          "brand": "", "keyword": None, "est_price": None,
                          "asin": "", "review_count": 0})
        sub["products"] = prods
    return spec
