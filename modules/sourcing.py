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

import re
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
_NODE_NONE = "1000"             # sentinel: no specific browse node guessed

# amazon.com browse-node ids keyed by short phrases — used by _guess_node() to
# pick a node from category/subcategory text when the LLM did not supply one.
NODE_DB: dict[str, str] = {
    # Pet Supplies
    "pet supplies": "2619533011", "dog supplies": "2619533011", "cat supplies": "2619533011",
    "fish aquarium": "2619534011", "bird supplies": "3606785011", "small animal": "3606786011",
    # Health & Beauty
    "vitamins supplements": "3774861", "health household": "3760901", "sports nutrition": "6973663011",
    "personal care": "11060451", "skin care": "11060451", "hair care": "11057771", "oral care": "3760931",
    # Kitchen
    "kitchen dining": "284507", "cookware": "289914", "bakeware": "289739", "kitchen tools": "289973",
    "small appliances": "298092", "coffee": "678508011",
    # Home
    "home kitchen": "1055398", "bedding": "3732961", "bath": "3610841", "furniture": "1063306",
    "storage organization": "3737461", "cleaning supplies": "3760901", "lighting": "495224", "led strip": "495224",
    # Fitness & Sports
    "sports outdoors": "3375251", "exercise fitness": "3407731", "yoga": "3407731",
    "camping hiking": "3375381", "cycling": "3403875", "running": "3375271",
    # Electronics
    "electronics": "172659", "headphones": "745384", "bluetooth speaker": "172659",
    "phone accessories": "2335752011", "laptop accessories": "541966", "smart home": "6563140011",
    "security camera": "172659", "power bank": "172659",
    # Baby
    "baby": "165797011", "baby care": "165797011", "diapering": "165796011",
    "feeding": "166585011", "baby toys": "165793011",
    # Clothing & Fashion
    "clothing": "7141123011", "mens clothing": "1036592", "womens clothing": "1045024",
    "shoes": "672123011", "accessories": "7141123011",
    # Office
    "office products": "1069242", "office supplies": "1069242", "desk accessories": "1069242",
    # Automotive
    "automotive": "15684181", "car accessories": "15684181", "car electronics": "15684181",
    # Outdoor & Garden
    "garden outdoor": "2972638011", "patio furniture": "3732961", "lawn care": "3238155011", "plants": "3238155011",
    # Toys & Games
    "toys games": "165793011", "board games": "166925011", "puzzles": "166943011", "outdoor play": "165793011",
    # Arts & Crafts
    "arts crafts": "2617942011", "painting": "2617942011", "sewing": "2617942011",
    # Food & Grocery
    "grocery food": "16310101", "snacks": "16310101", "beverages": "16310101", "organic food": "16310101",
}
_WORD_RE = re.compile(r"[a-z0-9]+")
# Words too generic to be a reliable category signal — their match is halved.
GENERIC_WORDS = {"home", "sport", "best", "new", "top", "kit", "set",
                 "pro", "mini", "portable", "premium", "compact", "plus", "product"}


def _ranked_nodes(text: str) -> list[tuple[str, str, float]]:
    """NODE_DB entries matching ``text``, best first as (node_id, key, score).

    Word-level scoring: a key word scores 2 for a whole-word match, 1 for a
    substring-only match — halved (1 / 0.5) when the word is in
    :data:`GENERIC_WORDS`. Ties broken by key specificity (more words). Empty
    list when nothing matches.
    """
    words = set(_WORD_RE.findall(text.lower()))
    if not words:
        return []
    scored: list[tuple[str, str, float, int]] = []
    for key, node in NODE_DB.items():
        key_words = key.split()
        score = 0.0
        for w in key_words:
            if w in words:
                hit = 2.0
            elif any(w in tw for tw in words):
                hit = 1.0
            else:
                continue
            score += hit * 0.5 if w in GENERIC_WORDS else hit
        if score > 0:
            scored.append((node, key, score, len(key_words)))
    scored.sort(key=lambda t: (t[2], t[3]), reverse=True)
    return [(node, key, score) for node, key, score, _ in scored]


def _guess_node(category: str, subcategory: str = "") -> str:
    """Best-effort Amazon browse-node id; :data:`_NODE_NONE` ("1000") if none."""
    ranked = _ranked_nodes(f"{category} {subcategory}")
    return ranked[0][0] if ranked else _NODE_NONE


def _get_node_candidates(category: str) -> str:
    """Top-5 distinct NODE_DB matches for ``category`` as a one-line string:
    ``"2619533011(pet supplies), 3774861(vitamins supplements), ..."`` —
    empty string when nothing matches.
    """
    seen: set[str] = set()
    out: list[str] = []
    for node, key, _ in _ranked_nodes(category):
        if node in seen:
            continue
        seen.add(node)
        out.append(f"{node}({key})")
        if len(out) >= 5:
            break
    return ", ".join(out)


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
        if self.amazon_node_id and self.amazon_node_id != _NODE_NONE:
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
    spark_rows: tuple[dict, ...] = ()   # filled by modules.spark_import.merge_with_sourcing


def generate_sourcing_list(category: str, n_subs: int = DEFAULT_SUBS,
                           n_variants: int = DEFAULT_VARIANTS) -> SourcingResult:
    n_subs = max(1, int(n_subs))
    n_variants = max(1, min(len(_VARIANT_POOL), int(n_variants)))
    spec = _normalize(_from_llm(category, n_subs), category, n_subs)
    variants = _VARIANT_POOL[:n_variants]
    rng = seeded_rng("sourcing-price", category)

    rows: list[SourcingRow] = []
    for sub in spec:
        node_id = (str(sub.get("amazon_node_id") or "").strip()
                   or _guess_node(category, sub["subcategory"]))
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


# LLM prompt template (filled by _from_llm with {category}, {n_subs},
# {products_n}, {candidates}). Literal JSON braces are doubled for str.format.
USER_PROMPT = (
    'For a dropshipping store in the "{category}" niche, propose {n_subs} '
    "subcategories. For each subcategory give:\n"
    "  amazon_node_id : 아래 후보 중 가장 적합한 노드 ID를 선택하세요. 확신이 없으면 빈 문자열.\n"
    "                   후보: {candidates}\n"
    'and list {products_n} specific product ideas; for each product give a '
    'likely incumbent "brand", a high-search-volume low-competition "keyword", '
    'a rough USD retail price "est_price", and if known an "asin" and '
    '"review_count" (else "" and 0). Return ONLY a JSON array: '
    '[{{"subcategory": "...", "amazon_node_id": "...", "products": [{{"name": '
    '"...", "brand": "...", "keyword": "...", "est_price": <num>, "asin": '
    '"...", "review_count": <int>}}, ...]}}, ...]. No prose.'
)


def _from_llm(category: str, n_subs: int) -> list[dict] | None:
    prompt = USER_PROMPT.format(
        category=category, n_subs=n_subs, products_n=PRODUCTS_N,
        candidates=_get_node_candidates(category) or "(없음 — 빈 문자열로 두세요)",
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
