"""Direct dataset-to-sourcing for high-volume Spark feeds.

Bypasses the LLM entirely: pulls top-N ASINs from the local HF
Amazon-Reviews-2023 SQLite index for each requested HF dataset category and
emits one :class:`SourcingRow` per ASIN. Compared to
:func:`modules.sourcing.generate_sourcing_list` this trades subcategory
naming, variant labels and brand inference for:

  * 100 percent ``/dp/{ASIN}`` URL coverage
  * deterministic output (no LLM variance)
  * sub-second generation for tens of thousands of rows
  * zero LLM token cost

Interface
---------
    bulk_sourcing_list(categories: list[str], n_per_cat: int = 1000)
        -> SourcingResult

``categories`` are user-facing labels (e.g. ``"wireless earbuds"`` or
``"Sports_and_Outdoors"``); each is routed through ``dataset_lookup`` so
both natural-language queries and raw HF category names work.
"""
from __future__ import annotations

from . import dataset_lookup, spark_urls
from .sourcing import SourcingResult, SourcingRow

DEFAULT_N_PER_CAT = 1000
HARD_CAP = 5000     # per category — protects SQLite query size + Excel render


def _rows_for_category(category: str, n: int) -> list[SourcingRow]:
    """Top-N ASINs for one category as :class:`SourcingRow` list.

    Recognises both raw HF category names (``"Pet_Supplies"``) — direct
    SQLite lookup, no keyword filter — and natural-language queries
    (``"dog toy"``) — routes through the keyword filter chain. Returns an
    empty list when neither yields data.
    """
    n = min(n, HARD_CAP)
    known = set(dataset_lookup.list_categories())
    if category in known:
        items = dataset_lookup.top_asins_direct(category, n=n) or []
    else:
        items = dataset_lookup.top_asins(category, n=n) or []
    out: list[SourcingRow] = []
    for it in items:
        asin = (it.get("asin") or "").strip().upper()
        if len(asin) != 10:
            continue
        title = (it.get("title") or "").strip()
        ds_cat = it.get("_dataset_category") or category
        try:
            price = float(it.get("est_price") or 0.0)
        except (TypeError, ValueError):
            price = 0.0
        out.append(SourcingRow(
            subcategory=ds_cat,
            base_product=title[:120] or f"ASIN {asin}",
            variant="",
            brand=(it.get("brand") or "").strip(),
            keyword="",
            est_price=round(price, 2),
            amazon_node_id="",
            asin=asin,
            review_count=int(it.get("review_count") or 0),
        ))
    return out


def bulk_sourcing_list(categories: list[str],
                       n_per_cat: int = DEFAULT_N_PER_CAT) -> SourcingResult:
    """Build a flat sourcing list across many categories at once.

    Output ordering: rows grouped by input ``categories`` order, within each
    category sorted by descending ``review_count`` (already from SQLite).
    Duplicate ASINs across categories are de-duplicated, keeping the first
    occurrence.
    """
    n_per_cat = max(1, min(int(n_per_cat), HARD_CAP))
    seen_asins: set[str] = set()
    rows: list[SourcingRow] = []
    per_cat_counts: dict[str, int] = {}
    for cat in categories:
        cat_rows = _rows_for_category(cat, n_per_cat)
        kept = 0
        for row in cat_rows:
            if row.asin in seen_asins:
                continue
            seen_asins.add(row.asin)
            rows.append(row)
            kept += 1
        per_cat_counts[cat] = kept

    label = ", ".join(f"{c} ({per_cat_counts.get(c, 0):,})"
                      for c in categories[:6])
    if len(categories) > 6:
        label += f", +{len(categories) - 6} more"
    summary = (
        f"Bulk Sourcing — {len(categories)}개 카테고리 × 최대 {n_per_cat:,} ASIN "
        f"= {len(rows):,} 유니크 행 (중복 ASIN 제거 후). 모든 행이 실 "
        f"`/dp/{{ASIN}}` URL. LLM 미사용 — 데이터셋 직접 추출. "
        f"내역: {label}."
    )
    return SourcingResult(
        category=" + ".join(categories[:3]) + (
            f" +{len(categories) - 3}" if len(categories) > 3 else ""),
        rows=tuple(rows),
        n_subs=len(categories),
        n_variants=1,
        total=len(rows),
        summary=summary,
    )


# SEO-friendly modifiers (replaced legacy "ideas/decor/for kids" which
# misfit niche categories like compression socks, wine accessories). Used
# only when n_variations exceeds the base 1 — first slot is always the raw
# query, then SEO-friendly anchors that preserve niche specificity.
_QUERY_MODIFIERS = ("", "best", "top rated", "premium", "amazon best seller",
                    "review", "popular", "set", "kit", "2026", "deal",
                    "bestseller", "highly rated", "trending", "for women",
                    "for men", "gift", "professional", "compact", "portable")


def spark_query_list(query: str, n_variations: int = 8,
                     include_broad: bool = False,
                     pages: int = 1) -> SourcingResult:
    """Spark URLs for a single user-typed query (e.g. ``"reading nook"``).

    Routes ``query`` through :func:`modules.dataset_lookup.map_category` to
    find the matching HF dataset category and its Amazon browse node, then
    emits ``n_variations`` keyword variations of the query — each becomes
    one Spark search URL focused on **this one niche**. ``pages>=2``
    multiplies that by expanding each into N paginated URLs.

    When ``include_broad=True``, also appends the mapped HF category's full
    ``HF_BROAD_KEYWORDS`` set — covers the niche's adjacent ecosystem (e.g.
    "reading nook" → Home_and_Kitchen broad: kitchen, bedding, lighting,
    decor, ...). Adds ~10~26 URLs depending on category size.
    """
    import re as _re
    q = _re.sub(r"\s*\([^)]*\)", "", query or "").strip()
    if not q:
        return SourcingResult(category="(empty query)", rows=(), n_subs=0,
                              n_variants=0, total=0,
                              summary="키워드를 입력하세요.")
    hf_cat = dataset_lookup.map_category(q)
    node = spark_urls.HF_TO_BROWSE_NODE.get(hf_cat or "", "")
    n = max(1, min(int(n_variations), len(_QUERY_MODIFIERS)))
    pages = max(1, int(pages))
    rows: list[SourcingRow] = []
    seen_kws: set[str] = set()
    for mod in _QUERY_MODIFIERS[:n]:
        kw = f"{q} {mod}".strip() if mod else q
        if kw.lower() in seen_kws:
            continue
        seen_kws.add(kw.lower())
        for page in range(1, pages + 1):
            rows.append(SourcingRow(
                subcategory=q, base_product=kw, variant="", brand="",
                keyword=kw, est_price=0.0,
                amazon_node_id=node, asin="", review_count=0, page=page,
            ))
    n_variations_rows = len(rows)
    if include_broad and hf_cat:
        for kw in spark_urls.HF_BROAD_KEYWORDS.get(hf_cat, []):
            if kw.lower() in seen_kws:
                continue
            seen_kws.add(kw.lower())
            for page in range(1, pages + 1):
                rows.append(SourcingRow(
                    subcategory=f"{hf_cat} (브로드)", base_product=kw,
                    variant="", brand="", keyword=kw, est_price=0.0,
                    amazon_node_id=node, asin="", review_count=0, page=page,
                ))
    broad_added = len(rows) - n_variations_rows
    page_note = f" × {pages}페이지" if pages > 1 else ""
    summary = (
        f"'{q}' 타겟 Spark URL — {n_variations_rows // pages}개 키워드 변형"
        f"{f' + {broad_added // pages}개 {hf_cat} 브로드' if broad_added else ''}"
        f"{page_note} = 총 **{len(rows)}개** URL. "
        f"매핑 HF: {hf_cat or '미매핑'}, 노드: {node or 'n/a'}. "
        f"예상 수확: ~{len(rows) * 60:,}+ 상품 (URL당 ~60)."
    )
    return SourcingResult(
        category=f"Spark targeted: {q}", rows=tuple(rows),
        n_subs=1, n_variants=1, total=len(rows), summary=summary,
    )


def spark_category_list(categories: list[str]) -> SourcingResult:
    """Spark-native broad-search rows — one per (HF category × keyword seed).

    Matches the Spark guide's "수집 링크" format: ``keywords=...&rh=n%3A...,
    p_n_has_afn_offer%3A1,p_85%3A2470955011``. Each URL paginates through
    hundreds-to-thousands of Prime+FBA products in its browse node, which
    is what the Spark scraper is built for (one URL = 6h crawl ≈ 900+
    products per the guide's example).
    """
    rows: list[SourcingRow] = []
    for cat in categories:
        node = spark_urls.HF_TO_BROWSE_NODE.get(cat)
        if not node:
            continue
        kws = spark_urls.HF_BROAD_KEYWORDS.get(
            cat, [cat.lower().replace("_", " ")])
        for kw in kws:
            rows.append(SourcingRow(
                subcategory=cat, base_product=kw, variant="",
                brand="", keyword=kw, est_price=0.0,
                amazon_node_id=node, asin="", review_count=0,
            ))
    label = f"{len(categories)}개 HF 카테고리 → {len(rows)} 브로드 검색 URL"
    summary = (
        f"Spark-네이티브 모드 — {label}. 각 URL은 keyword + 브라우즈노드 + "
        f"Prime + AFN 필터 조합 (스파크 가이드 11/24 형식). URL당 페이지네이션 "
        f"통해 수백~수천 베스트셀러 수확 예상 (6시간 ≈ 900개/URL이 가이드 기준)."
    )
    return SourcingResult(
        category=f"Spark broad ({len(categories)} cats)",
        rows=tuple(rows), n_subs=len(categories), n_variants=1,
        total=len(rows), summary=summary,
    )
