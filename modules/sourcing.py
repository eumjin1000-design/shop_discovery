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

from . import sources
from .llm import ask_json
from .util import seeded_rng

PRODUCTS_N = 5                 # products per subcategory (fixed)
DEFAULT_SUBS = 6
DEFAULT_VARIANTS = 5
_VARIANT_POOL = ["Standard", "Compact", "Premium", "Set of 2", "Travel Size",
                 "Mini", "XL", "Refill Pack", "Gift Box", "Pro"]
_PRIME_NODE_US = "23533298011"  # p_n_prime_eligibility filter id on amazon.com
_NODE_NONE = "1000"             # sentinel: no specific browse node guessed

from .sourcing_nodes import NODE_DB
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
        """Real product page when a valid ``asin`` is set, else a browse-node
        search (Prime, sorted by review count), else a keyword search.
        """
        a = (self.asin or "").strip().upper()
        if re.fullmatch(r"[A-Z0-9]{10}", a):
            return f"https://www.amazon.com/dp/{a}"
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


# LLM prompt template. Literal JSON braces are doubled for str.format.
USER_PROMPT = (
    'For a dropshipping store in the "{category}" niche, propose {n_subs} '
    "subcategories. For each subcategory give:\n"
    "  amazon_node_id : 아래 후보 중 가장 적합한 노드 ID를 선택하세요. 확신이 없으면 빈 문자열.\n"
    "                   후보: {candidates}\n"
    'and list {products_n} specific product ideas. {real_block}'
    'For each product give a likely incumbent "brand", a high-search-volume '
    'low-competition "keyword", a USD retail "est_price", and "asin" + '
    '"review_count". When a product matches an entry in REAL_PRODUCTS above, '
    'COPY its exact asin/brand/est_price/review_count verbatim — do not invent. '
    'Only invent asin="" / review_count=0 when no real match exists. '
    'Return ONLY a JSON array: '
    '[{{"subcategory": "...", "amazon_node_id": "...", "products": [{{"name": '
    '"...", "brand": "...", "keyword": "...", "est_price": <num>, "asin": '
    '"...", "review_count": <int>}}, ...]}}, ...]. No prose.'
)


def _real_products_block(category: str, n_subs: int) -> str:
    """Pre-fetched real top sellers as a prompt block; ``""`` when no source
    is available. Tries the local HF dataset first (free, offline) and falls
    back to Keepa (paid, live).
    """
    target = max(15, n_subs * PRODUCTS_N)
    rows = (sources.dataset_top_asins(category, n=target)
            or sources.keepa_top_asins(category, n=target)
            or [])
    if not rows:
        return ""
    lines = [
        f"- {r['asin']} | {r.get('brand') or '?'} | "
        f"${r.get('est_price') or '?'} | {r.get('review_count') or 0} reviews | "
        f"{r.get('title') or ''}"
        for r in rows
    ]
    return ("REAL_PRODUCTS (real Amazon best sellers — assign these ASINs to "
            f"the most appropriate subcategory):\n" + "\n".join(lines) + "\n")


def _from_llm(category: str, n_subs: int) -> list[dict] | None:
    prompt = USER_PROMPT.format(
        category=category, n_subs=n_subs, products_n=PRODUCTS_N,
        candidates=_get_node_candidates(category) or "(없음 — 빈 문자열로 두세요)",
        real_block=_real_products_block(category, n_subs),
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
