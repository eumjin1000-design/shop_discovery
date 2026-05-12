"""Step 4 - mine existing product reviews for gaps and complaints.

A low average rating with recurring, fixable complaints is a *good* sign for a
dropshipper: it means the incumbent products underdeliver and a better-curated
offer can win. Mock implementation for now; the LLM is used (when available)
to turn the category into plausible complaint themes.

Interface
---------
    mine_reviews(category: str, keywords: tuple[Keyword, ...]) -> ReviewResult
"""
from __future__ import annotations

from .llm import ask_json, is_available
from .models import Keyword, ReviewResult
from .util import clamp, seeded_rng

# TODO: scrape / API-pull real reviews (Amazon, AliExpress, Trustpilot...).

_GENERIC_COMPLAINTS = (
    "stops working after a few weeks",
    "smaller than expected",
    "confusing instructions",
    "cheap-feeling materials",
    "slow or expensive shipping",
)


def mine_reviews(category: str, keywords: tuple[Keyword, ...]) -> ReviewResult:
    rng = seeded_rng("review", category)

    reviews_analyzed = rng.choice([180, 420, 760, 1500, 3200])
    avg_rating = round(rng.uniform(3.1, 4.6), 2)
    # Lower rating -> larger share of negative reviews.
    negative_ratio = round(clamp((5.0 - avg_rating) / 4.0 * rng.uniform(0.8, 1.2)), 3)

    complaints = _llm_complaints(category) or list(_GENERIC_COMPLAINTS)
    rng.shuffle(complaints)
    top_complaints = tuple(complaints[:5])

    quality = "weak incumbents - clear opening" if avg_rating < 4.0 else (
        "decent incumbents - must out-execute" if avg_rating < 4.4 else
        "strong incumbents - hard to beat"
    )
    notes = (
        f"Avg rating {avg_rating}/5 across ~{reviews_analyzed:,} reviews, "
        f"{negative_ratio*100:.0f}% negative ({quality}). "
        f"{'[complaints via LLM] ' if is_available() else ''}[mock metrics]"
    )
    return ReviewResult(
        reviews_analyzed=reviews_analyzed,
        avg_rating=avg_rating,
        negative_ratio=negative_ratio,
        top_complaints=top_complaints,
        notes=notes,
    )


def _llm_complaints(category: str) -> list[str]:
    if category in _llm_complaints.cache:  # type: ignore[attr-defined]
        return _llm_complaints.cache[category]  # type: ignore[attr-defined]
    prompt = (
        f'List 5 common customer complaints about "{category}" products sold '
        "online. Return ONLY a JSON array of short strings."
    )
    data = ask_json(prompt)
    result: list[str] = []
    if isinstance(data, list):
        result = [str(x).strip() for x in data if str(x).strip()][:5]
    _llm_complaints.cache[category] = result  # type: ignore[attr-defined]
    return result


_llm_complaints.cache = {}  # type: ignore[attr-defined]
