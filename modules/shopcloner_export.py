"""Export a shop_discovery analysis into ShopCloner's universal-seo-schema JSON.

ShopCloner (separate Electron app) consumes a JSON of the shape produced by its
``pdf-analyzer`` and applied by ``seo-applier``:

    { shop_concept{name,niche,tag,target,tone},
      mega_keyword{primary,volume,kd,alternatives[]},
      gem_keywords[{keyword,volume,kd,category,matching_products[]}],
      categories[{name,h1,title_tag,meta_description,keywords[]}],
      blog_topics[] }

This bridge maps a :class:`~modules.models.PipelineResult` (and an optional
:class:`~modules.sourcing.SourcingResult` for the category list) into that
schema so a GO category can be handed straight to ShopCloner's Phase 2.

KD (keyword difficulty) is not tracked per keyword here, so it is estimated
once at the category level from the Amazon competing-listing count (BSR step).

Interface
---------
    to_universal_schema(result, shop_name=None, sourcing_result=None) -> dict
    schema_json_bytes(schema) -> bytes
"""
from __future__ import annotations

import json
import re

from .models import PipelineResult


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-") or "shop"


def _kd_from_bsr(competing_listings: int) -> int:
    """Estimate keyword difficulty (0-100) from Amazon competing-listing count.

    More listings = more saturated = harder. Tiers mirror the BSR competition
    buckets used by :mod:`modules.synthesizer`. Category-level estimate applied
    to every keyword (per-keyword KD is not available in this pipeline).
    """
    c = int(competing_listings or 0)
    if c < 1500:
        return 15
    if c < 5000:
        return 30
    if c < 10000:
        return 45
    if c < 25000:
        return 60
    if c < 50000:
        return 75
    return 85


def _target_from_intent(result: PipelineResult) -> str:
    age = (getattr(result.intent, "primary_age", "") or "").strip()
    return f"US shoppers aged {age}" if age else "US online shoppers"


def _categories_from_sourcing(sourcing_result) -> list[dict]:
    """Group sourcing rows by subcategory → ShopCloner categories[].

    ``h1``/``title_tag``/``meta_description`` are left blank so ShopCloner's
    AI fills them (gem-keyword-enhanced) at apply time.
    """
    by_sub: dict[str, list[str]] = {}
    for row in getattr(sourcing_result, "rows", ()):  # SourcingRow
        sub = row.subcategory
        kw = (row.keyword or "").strip()
        bucket = by_sub.setdefault(sub, [])
        if kw and kw not in bucket:
            bucket.append(kw)
    cats = []
    for sub, kws in by_sub.items():
        cats.append({"name": sub, "h1": "", "title_tag": "",
                     "meta_description": "", "keywords": kws[:8]})
    return cats


def to_universal_schema(result: PipelineResult, shop_name: str | None = None,
                        sourcing_result=None) -> dict:
    """Map a PipelineResult into ShopCloner's universal-seo-schema dict."""
    category = result.request.category
    kws = sorted(result.keywords, key=lambda k: k.est_monthly_volume or 0, reverse=True)
    kd = _kd_from_bsr(getattr(result.bsr, "competing_listings", 0))

    name = (shop_name or "").strip() or f"{category} Store"
    shop_concept = {
        "name": name,
        "niche": f"{category} for the US market",
        "tag": _slug(category),
        "target": _target_from_intent(result),
        "tone": "Trustworthy, helpful, expert",
    }

    primary = kws[0] if kws else None
    mega_keyword = {
        "primary": primary.term if primary else category,
        "volume": int(primary.est_monthly_volume) if primary else 0,
        "kd": kd,
        "alternatives": [
            {"keyword": k.term, "volume": int(k.est_monthly_volume or 0), "kd": kd}
            for k in kws[1:4]
        ],
    }

    gem_keywords = [
        {"keyword": k.term, "volume": int(k.est_monthly_volume or 0), "kd": kd,
         "category": "", "matching_products": []}
        for k in kws
    ]

    categories = (_categories_from_sourcing(sourcing_result)
                  if sourcing_result is not None else
                  [{"name": category, "h1": "", "title_tag": "",
                    "meta_description": "", "keywords": [k.term for k in kws][:8]}])

    return {
        "shop_concept": shop_concept,
        "mega_keyword": mega_keyword,
        "gem_keywords": gem_keywords,
        "categories": categories,
        "blog_topics": [],   # ShopCloner generates these via Gemini when empty
    }


def schema_json_bytes(schema: dict) -> bytes:
    """UTF-8 JSON bytes (pretty) for a Streamlit download_button."""
    return json.dumps(schema, ensure_ascii=False, indent=2).encode("utf-8")
