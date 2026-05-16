"""Build a sourcing list for a GO-rated category.

Sized ``n_subs × PRODUCTS_N × n_variants × pages``. Each row carries:
subcategory, base product, variant, an estimated incumbent brand, a
high-search-volume / low-competition keyword, an estimated USD price, an
Amazon **browse-node** search URL (Prime-eligible, sorted by review count,
optionally ``&page=N``), plus ``asin`` / ``review_count`` placeholders the
scraper (Spark) fills in later.

Subcategory + product ideas come from Claude/Gemini when available
(``passes>1`` issues multiple LLM calls and dedups by subcategory name).
Otherwise a deterministic template fallback is used. Prices use a
category-seeded RNG so a given category always yields the same numbers.

Interface
---------
    generate_sourcing_list(category, n_subs=6, n_variants=5,
                           passes=1, pages=1, verify_urls=False)
        -> SourcingResult
"""
from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass

from .sourcing_llm import (PRODUCTS_N, from_llm_multipass, normalize_spec)
from .sourcing_nodes import NODE_DB
from .util import seeded_rng

DEFAULT_SUBS = 6
DEFAULT_VARIANTS = 5
DEFAULT_PASSES = 1
DEFAULT_PAGES = 1
_VARIANT_POOL = ["Standard", "Compact", "Premium", "Set of 2", "Travel Size",
                 "Mini", "XL", "Refill Pack", "Gift Box", "Pro",
                 "Set of 4", "Bulk Pack", "Deluxe", "Eco", "Smart",
                 "Foldable", "Heavy Duty", "Lightweight", "Limited Edition",
                 "Bundle"]
_PRIME_NODE_US = "23533298011"
_NODE_NONE = "1000"

_WORD_RE = re.compile(r"[a-z0-9]+")
# Words too generic to be a reliable category signal — match halved.
GENERIC_WORDS = {"home", "sport", "best", "new", "top", "kit", "set",
                 "pro", "mini", "portable", "premium", "compact", "plus", "product"}


def _ranked_nodes(text: str) -> list[tuple[str, str, float]]:
    """NODE_DB matches for ``text``, best first as (node_id, key, score).
    Requires >=50% of key words to match so generic words alone don't
    misroute (e.g. ``"accessories"`` alone won't grab phone-accessories)."""
    words = set(_WORD_RE.findall(text.lower()))
    if not words:
        return []
    scored: list[tuple[str, str, float, int]] = []
    for key, node in NODE_DB.items():
        key_words = key.split()
        score = 0.0
        hits = 0
        for w in key_words:
            if w in words:
                hit = 2.0
            elif any(w in tw for tw in words):
                hit = 1.0
            else:
                continue
            hits += 1
            score += hit * 0.5 if w in GENERIC_WORDS else hit
        if score > 0 and hits / len(key_words) > 0.5:
            scored.append((node, key, score, len(key_words)))
    scored.sort(key=lambda t: (t[2], t[3]), reverse=True)
    return [(node, key, score) for node, key, score, _ in scored]


def _strip_annotation(text: str) -> str:
    """Strip ``(annotation)`` so CURATED names like ``"Car accessories
    (organizer, phone mount)"`` don't leak words to wrong NODE_DB keys."""
    return re.sub(r"\s*\([^)]*\)", "", text or "").strip()


def _guess_node(category: str, subcategory: str = "") -> str:
    ranked = _ranked_nodes(
        f"{_strip_annotation(category)} {_strip_annotation(subcategory)}")
    return ranked[0][0] if ranked else _NODE_NONE


def _get_node_candidates(category: str) -> str:
    """Top-5 distinct NODE_DB matches as ``"node(key), node(key), ..."``."""
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
    page: int = 1               # search-URL pagination (1 = first page)

    @property
    def product_name(self) -> str:
        return f"{self.base_product} ({self.variant})"

    @property
    def amazon_url(self) -> str:
        a = (self.asin or "").strip().upper()
        if re.fullmatch(r"[A-Z0-9]{10}", a):
            return f"https://www.amazon.com/dp/{a}"
        if self.amazon_node_id and self.amazon_node_id != _NODE_NONE:
            rh = (f"n%3A{urllib.parse.quote(str(self.amazon_node_id))}"
                  f"%2Cp_n_prime_eligibility%3A{_PRIME_NODE_US}")
            page_suffix = f"&page={self.page}" if self.page >= 2 else ""
            return (f"https://www.amazon.com/s?rh={rh}"
                    f"&s=review-count-rank{page_suffix}")
        q = urllib.parse.quote_plus(f"{self.base_product} {self.variant}")
        page_suffix = f"&page={self.page}" if self.page >= 2 else ""
        return f"https://www.amazon.com/s?k={q}&s=review-count-rank{page_suffix}"

    @property
    def search_url(self) -> str:
        """Spark-native search URL — node + Prime + AFN filters + optional
        ``&page=N``. See :mod:`modules.spark_urls`."""
        from .spark_urls import build_search_url
        return build_search_url(self.keyword, self.brand, self.base_product,
                                self.amazon_node_id, page=self.page)


@dataclass(frozen=True)
class SourcingResult:
    category: str
    rows: tuple[SourcingRow, ...]
    n_subs: int
    n_variants: int
    total: int
    summary: str
    spark_rows: tuple[dict, ...] = ()   # filled by modules.spark_import


def generate_sourcing_list(category: str, n_subs: int = DEFAULT_SUBS,
                           n_variants: int = DEFAULT_VARIANTS,
                           passes: int = DEFAULT_PASSES,
                           pages: int = DEFAULT_PAGES,
                           verify_urls: bool = False) -> SourcingResult:
    """Build the sourcing list.

    ``passes>=2`` issues that many LLM calls and dedups by subcategory name
    (case-insensitive) — yields up to ``n_subs × passes`` distinct subs.
    ``pages>=2`` emits each row that many times, each with a different
    ``&page=N`` suffix on its search URL — Spark visits all without per-URL
    pagination config. Defaults (1/1) preserve legacy behaviour.
    """
    category = _strip_annotation(category)
    n_subs = max(1, int(n_subs))
    n_variants = max(1, min(len(_VARIANT_POOL), int(n_variants)))
    passes = max(1, int(passes))
    pages = max(1, int(pages))

    spec = normalize_spec(
        from_llm_multipass(category, n_subs, _get_node_candidates,
                           verify_urls=verify_urls, passes=passes),
        category, n_subs * passes, _strip_annotation,
    )
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
                for page in range(1, pages + 1):
                    rows.append(SourcingRow(
                        subcategory=sub["subcategory"],
                        base_product=prod["name"], variant=variant,
                        brand=brand, keyword=keyword, est_price=price,
                        amazon_node_id=node_id, asin=asin, review_count=rc,
                        page=page,
                    ))

    total = len(rows)
    actual_subs = len(spec)
    warn = ("" if any(r.asin for r in rows) else
            " ⚠️ 데이터셋 미매핑 → 일반 검색 URL만 생성됩니다. 대량 수확은 "
            "**🎯 대량 소싱 모드 → Spark 카테고리 URL**을 사용하세요.")
    pass_note = f" × {passes}패스" if passes > 1 else ""
    page_note = f" × {pages}페이지" if pages > 1 else ""
    summary = (
        f"{category} 소싱 — {actual_subs}개 서브{pass_note} × "
        f"{PRODUCTS_N}상품 × {n_variants}변형{page_note} = **{total}개**. "
        "Amazon URL = 노드 + Prime + 리뷰순; brand 추정." + warn
    )
    return SourcingResult(category=category, rows=tuple(rows), n_subs=actual_subs,
                          n_variants=n_variants, total=total, summary=summary)
