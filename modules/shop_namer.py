"""Generate brandable store-name ideas for a GO-rated category.

Uses Claude when available; otherwise falls back to a deterministic template
so the feature still works offline.

Interface
---------
    generate_shop_names(category: str, n: int = 5) -> list[ShopName]
"""
from __future__ import annotations

from dataclasses import dataclass

from .llm import ask_json
from .util import seeded_rng

_SUFFIXES = ["Hub", "Nest", "Lane", "Co", "Loop", "Den", "Cove", "Vault", "Bay", "Forge"]

# TLD diversity. Top-row .com/.co/.shop/.store are clean retail TLDs; the rest
# are fallbacks when the bare slug is taken on .com (very common for short
# brand names).
_TLDS = (".com", ".co", ".shop", ".store", ".io", ".app", ".us")
# Prefix variants for when the bare slug is taken on .com.
_PREFIXES = ("get", "shop", "the", "hello", "my")


def _slug(name: str) -> str:
    return "".join(ch for ch in str(name or "").lower() if ch.isalnum())


def _domain_candidates(name: str, max_n: int = 8) -> list[str]:
    """Diverse domain candidates mixing TLD variation and prefixed .com.

    Bare .com is almost always taken for short brand words, so this returns
    a mix of (a) the bare slug across retail-friendly TLDs and (b) prefixed
    .com variants. Order interleaves both kinds so users see real diversity
    even if they only look at the top few.
    """
    slug = _slug(name)
    if not slug:
        return []
    # Interleaved: clean TLDs first, then prefixed .com, then techy TLDs.
    cands = [
        f"{slug}.com", f"{slug}.co", f"{slug}.shop", f"{slug}.store",
        f"get{slug}.com", f"shop{slug}.com",
        f"{slug}.io", f"the{slug}.com", f"{slug}.app",
        f"hello{slug}.com", f"my{slug}.com", f"{slug}.us", f"{slug}.net",
    ]
    seen: set[str] = set()
    return [d for d in cands if not (d in seen or seen.add(d))][:max_n]


@dataclass(frozen=True)
class ShopName:
    name: str
    concept: str

    @property
    def domain(self) -> str:
        """Primary candidate (backward compat) — bare slug + .com."""
        return f"{_slug(self.name)}.com"

    @property
    def domains(self) -> list[str]:
        """Diverse candidate list across multiple TLDs + prefixed variants."""
        return _domain_candidates(self.name)


def generate_shop_names(category: str, n: int = 5) -> list[ShopName]:
    return _from_llm(category, n) or _fallback(category, n)


def _from_llm(category: str, n: int) -> list[ShopName]:
    prompt = (
        f"Suggest {n} brandable e-commerce store names for a dropshipping store "
        f'selling "{category}". Requirements: English; short (4-10 chars) and '
        "easy to remember; 1-2 words, no hyphens or numbers; INVENTED or rare "
        "compound words preferred (bare .com is almost never available for "
        "common words, so prioritise uniqueness over generic dictionary terms). "
        "Domain candidates will be tried across .com/.co/.shop/.store/.io/.app/.us "
        "plus prefixed variants (get-, shop-, the-), so don't restrict to .com. "
        "For each give a one-line concept. Return ONLY a JSON array: "
        '[{"name": "...", "concept": "..."}]. No prose.'
    )
    data = ask_json(prompt, tier="quality", max_tokens=800)
    if not isinstance(data, list):
        return []
    out: list[ShopName] = []
    for item in data[:n]:
        if isinstance(item, dict) and str(item.get("name", "")).strip():
            out.append(ShopName(str(item["name"]).strip(),
                                str(item.get("concept", "")).strip()))
    return out


def _fallback(category: str, n: int) -> list[ShopName]:
    rng = seeded_rng("shopname", category)
    word = category.split()[0].capitalize() if category.split() else "Shop"
    sufs = rng.sample(_SUFFIXES, min(n, len(_SUFFIXES)))
    return [ShopName(f"{word}{s}", f"'{category}' 전문 스토어 — {s} 컨셉 (오프라인 폴백)")
            for s in sufs]
