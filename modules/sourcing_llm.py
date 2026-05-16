"""LLM-side helpers for :mod:`modules.sourcing` — extracted to keep that
module under the 300-line hard limit.

Public surface
--------------
* :func:`from_llm_multipass`  — call :func:`_from_llm` ``passes`` times, merge
  results by subcategory name (case-insensitive dedup). One pass = legacy.
* :func:`normalize_spec`      — coerce a spec list to exactly ``n_subs`` ×
  ``PRODUCTS_N`` shape (mirrors the old in-file ``_normalize``).
* :data:`PRODUCTS_N`          — re-exported so callers have one import line.
"""
from __future__ import annotations

from typing import Callable

from . import sources
from .llm import ask_json

PRODUCTS_N = 5

# Universal SEO-friendly modifiers (replaces prev "ideas/for kids/decor"
# which mis-fit categories like compression socks or wine accessories).
_FALLBACK_MODIFIERS = ("", "best", "top rated", "premium",
                       "amazon best seller", "review", "popular", "set",
                       "kit", "2026")


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
    '"...", "review_count": <int>}}, ...]}}, ...]. No prose.{seed_note}'
)


def _real_products_block(category: str, n_subs: int,
                         verify_urls: bool = False) -> str:
    target = max(15, n_subs * PRODUCTS_N)
    rows = sources.dataset_top_asins(category, n=target)
    if rows and verify_urls:
        from . import dataset_verify
        rows = dataset_verify.verify_asins(rows, max_check=min(30, len(rows)),
                                           drop_dead=True)
    if not rows:
        rows = sources.keepa_top_asins(category, n=target) or []
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


def _from_llm(category: str, n_subs: int, candidates_fn: Callable[[str], str],
              verify_urls: bool, pass_idx: int) -> list[dict] | None:
    """One LLM pass. ``pass_idx >= 2`` adds a diversification note so repeat
    calls return distinct subcategories instead of recycling pass 1."""
    seed_note = ("" if pass_idx < 2 else
                 f" Note: this is pass #{pass_idx} — propose DIFFERENT "
                 "subcategories from common ones (assume earlier passes "
                 "already covered the obvious ones).")
    prompt = USER_PROMPT.format(
        category=category, n_subs=n_subs, products_n=PRODUCTS_N,
        candidates=candidates_fn(category) or "(없음 — 빈 문자열로 두세요)",
        real_block=_real_products_block(category, n_subs, verify_urls),
        seed_note=seed_note,
    )
    data = ask_json(prompt, max_tokens=6000)
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


def from_llm_multipass(category: str, n_subs: int,
                       candidates_fn: Callable[[str], str],
                       verify_urls: bool = False,
                       passes: int = 1) -> list[dict] | None:
    """Multi-pass LLM with subcategory-name dedup.

    Each pass asks for ``n_subs`` subcategories; later passes (pass_idx >= 2)
    receive a diversification hint. Subcategories whose name (lower-cased) is
    already accumulated are skipped, so the final list contains up to
    ``n_subs * passes`` distinct subs. ``None`` if every pass failed.
    """
    passes = max(1, int(passes))
    merged: list[dict] = []
    seen_names: set[str] = set()
    for i in range(passes):
        spec = _from_llm(category, n_subs, candidates_fn, verify_urls, i + 1)
        if not spec:
            continue
        for sub in spec:
            key = str(sub.get("subcategory", "")).strip().lower()
            if not key or key in seen_names:
                continue
            seen_names.add(key)
            merged.append(sub)
    return merged or None


def fallback_spec(category: str, n_subs: int,
                  strip_fn: Callable[[str], str]) -> list[dict]:
    """LLM-failure fallback — ``"{cat} {modifier}"`` real searchable keywords."""
    cat = strip_fn(category)
    out: list[dict] = []
    for i in range(n_subs):
        kw = f"{cat} {_FALLBACK_MODIFIERS[i % len(_FALLBACK_MODIFIERS)]}".strip()
        out.append({"subcategory": kw, "amazon_node_id": "", "products": [
            {"name": kw, "brand": "", "keyword": kw.lower(),
             "est_price": None, "asin": "", "review_count": 0}
            for _ in range(PRODUCTS_N)]})
    return out


def normalize_spec(spec: list[dict] | None, category: str, n_subs: int,
                   strip_fn: Callable[[str], str]) -> list[dict]:
    """Coerce ``spec`` to exactly ``n_subs`` × :data:`PRODUCTS_N` shape."""
    fb = fallback_spec(category, n_subs, strip_fn)
    spec = list(spec or fb)[:n_subs]
    while len(spec) < n_subs:
        spec.append(fb[len(spec)])
    for sub in spec:
        sub.setdefault("amazon_node_id", "")
        prods = list(sub.get("products", []))[:PRODUCTS_N]
        while len(prods) < PRODUCTS_N:
            prods.append({"name": sub["subcategory"], "brand": "",
                          "keyword": str(sub["subcategory"]).lower(),
                          "est_price": None, "asin": "", "review_count": 0})
        sub["products"] = prods
    return spec
