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

# Modifier templates for long-tail expansion when n > 50. Each combines with
# every LLM seed AND the bare category to multiply coverage.
_PREFIX_MODS = (
    "best", "top rated", "cheap", "affordable", "premium", "modern",
    "professional", "lightweight", "compact", "portable", "smart",
    "wireless", "minimalist", "eco friendly",
)
_SUFFIX_MODS = (
    "reviews", "amazon", "for sale", "for home", "for office", "for travel",
    "for women", "for men", "for beginners", "set", "kit", "bundle",
    "alternative", "accessories", "gift", "online", "near me", "deals",
)
_SEED_TARGET_FOR_EXPANSION = 50  # LLM seeds we ask for in expanded mode


def generate_keywords(request: DiscoveryRequest, n: int = 8) -> tuple[Keyword, ...]:
    """Generate ``n`` keywords for ``request``.

    For ``n <= 50``: a single LLM call returns ``n`` keywords directly.
    For ``n > 50``: ask the LLM for ``_SEED_TARGET_FOR_EXPANSION`` diverse seeds,
    then deterministically expand each seed (and the bare category) with the
    prefix/suffix modifier templates above. The result is deduped (case-
    insensitive) and trimmed to exactly ``n``. Seed-derived long-tails inherit
    an attenuated volume estimate from their parent so downstream ranking still
    works when only the top few keywords receive real Google Trends data.
    """
    category = request.category.strip()
    if n <= 50:
        return _from_llm(category, n) or _fallback(category, n)

    seeds = _from_llm(category, _SEED_TARGET_FOR_EXPANSION) or _fallback(category, 10)
    return _expand(seeds, n, category)


def _expand(seeds: tuple[Keyword, ...], target_n: int, category: str
            ) -> tuple[Keyword, ...]:
    seen: set[str] = set()
    out: list[Keyword] = []

    def add(term: str, rationale: str, volume: int = 0) -> bool:
        key = term.lower().strip()
        if not key or key in seen:
            return False
        seen.add(key)
        out.append(Keyword(term=term.strip(), rationale=rationale,
                           est_monthly_volume=max(0, int(volume))))
        return len(out) >= target_n

    # 1) Original LLM seeds (highest signal — keep their volume estimates).
    for s in seeds:
        if add(s.term, s.rationale, s.est_monthly_volume):
            return tuple(out)
    # 2) Bare-category modifier variants — broad coverage.
    for p in _PREFIX_MODS:
        if add(f"{p} {category}", "category prefix modifier"):
            return tuple(out)
    for sfx in _SUFFIX_MODS:
        if add(f"{category} {sfx}", "category suffix modifier"):
            return tuple(out)
    # 3) Each seed × modifiers — deep long-tail expansion.
    for s in seeds:
        inherited = max(1, s.est_monthly_volume // 3)
        for p in _PREFIX_MODS:
            if add(f"{p} {s.term}", f"long-tail of '{s.term}'", inherited):
                return tuple(out)
        for sfx in _SUFFIX_MODS:
            if add(f"{s.term} {sfx}", f"long-tail of '{s.term}'", inherited):
                return tuple(out)
    return tuple(out)


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
