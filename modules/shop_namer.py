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


@dataclass(frozen=True)
class ShopName:
    name: str
    concept: str

    @property
    def domain(self) -> str:
        slug = "".join(ch for ch in self.name.lower() if ch.isalnum())
        return f"{slug}.com"


def generate_shop_names(category: str, n: int = 5) -> list[ShopName]:
    return _from_llm(category, n) or _fallback(category, n)


def _from_llm(category: str, n: int) -> list[ShopName]:
    prompt = (
        f"Suggest {n} brandable e-commerce store names for a dropshipping store "
        f'selling "{category}". Requirements: English; short and easy to '
        "remember; 1-2 words, no hyphens or numbers; a .com domain is plausibly "
        "available. For each give a one-line concept. Return ONLY a JSON array: "
        '[{"name": "...", "concept": "..."}]. No prose.'
    )
    data = ask_json(prompt, max_tokens=800)
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
