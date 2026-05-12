"""Step 1 — turn a raw category into a focused set of search keywords.

Uses the Anthropic API when available; otherwise falls back to a template
expansion so the pipeline still produces sensible keywords offline.

Interface
---------
    generate_keywords(request: DiscoveryRequest, n: int = 8) -> tuple[Keyword, ...]
"""
from __future__ import annotations

from .llm import ask_json
from .models import DiscoveryRequest, Keyword

_FALLBACK_MODIFIERS = [
    ("best {c}", "broad commercial query"),
    ("{c} for home", "use-case framing"),
    ("portable {c}", "feature angle - portability"),
    ("{c} reviews", "research-stage buyers"),
    ("cheap {c}", "price-sensitive segment"),
    ("{c} gift", "gifting occasion"),
    ("rechargeable {c}", "feature angle - power"),
    ("{c} alternative", "switchers from a competitor"),
    ("mini {c}", "form-factor variant"),
    ("{c} accessories", "attach / upsell demand"),
]


def generate_keywords(request: DiscoveryRequest, n: int = 8) -> tuple[Keyword, ...]:
    category = request.category.strip()
    llm = _from_llm(category, n)
    if llm:
        return llm
    return _fallback(category, n)


def _from_llm(category: str, n: int) -> tuple[Keyword, ...]:
    prompt = (
        f"You are a dropshipping product researcher. For the category "
        f'"{category}", list the {n} most commercially valuable search '
        "keywords a buyer would actually type. Return ONLY a JSON array of "
        'objects: [{"term": "...", "rationale": "...", '
        '"est_monthly_volume": <integer estimate>}]. No prose.'
    )
    data = ask_json(prompt)
    if not isinstance(data, list):
        return ()
    out: list[Keyword] = []
    for item in data[:n]:
        if not isinstance(item, dict) or "term" not in item:
            continue
        try:
            volume = int(item.get("est_monthly_volume") or 0)
        except (TypeError, ValueError):
            volume = 0
        out.append(
            Keyword(
                term=str(item["term"]).strip(),
                rationale=str(item.get("rationale", "")).strip(),
                est_monthly_volume=max(0, volume),
            )
        )
    return tuple(out)


def _fallback(category: str, n: int) -> tuple[Keyword, ...]:
    out: list[Keyword] = []
    for template, rationale in _FALLBACK_MODIFIERS[:n]:
        out.append(
            Keyword(
                term=template.format(c=category),
                rationale=rationale + " (offline fallback - no LLM)",
            )
        )
    return tuple(out)
