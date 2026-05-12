"""Step 5 - estimate commercial purchase intent behind the keywords.

Distinguishes "ready to buy" demand (e.g. "buy X online", "best X 2026") from
purely informational interest. Uses the LLM when available; otherwise scores
keywords with a small lexicon of intent markers.

Interface
---------
    check_intent(category: str, keywords: tuple[Keyword, ...]) -> IntentResult
"""
from __future__ import annotations

from .llm import ask_json
from .models import IntentResult, Keyword
from .util import clamp

_BUY_MARKERS = ("buy", "price", "cheap", "deal", "discount", "best", "shop",
                "for sale", "order", "coupon")
_PROBLEM_MARKERS = ("how to", "fix", "without", "vs", "alternative", "review",
                    "problem", "stop", "prevent", "remove")


def check_intent(category: str, keywords: tuple[Keyword, ...]) -> IntentResult:
    llm = _from_llm(category, keywords)
    if llm:
        return llm
    return _heuristic(keywords)


def _from_llm(category: str, keywords: tuple[Keyword, ...]) -> IntentResult | None:
    terms = ", ".join(kw.term for kw in keywords)
    prompt = (
        f'Audience research for the category "{category}". Given these search '
        f"terms: {terms}\nEstimate two ratios in 0..1: commercial_intent "
        "(share of terms from people ready to buy) and problem_awareness "
        "(share from people actively seeking a solution). Also give 3 example "
        'high-intent queries. Return ONLY JSON: {"commercial_intent": x, '
        '"problem_awareness": y, "sample_queries": ["...", "...", "..."]}.'
    )
    data = ask_json(prompt)
    if not isinstance(data, dict):
        return None
    try:
        ci = clamp(float(data.get("commercial_intent", 0)))
        pa = clamp(float(data.get("problem_awareness", 0)))
    except (TypeError, ValueError):
        return None
    samples = tuple(
        str(q).strip() for q in data.get("sample_queries", []) if str(q).strip()
    )[:3]
    return IntentResult(
        commercial_intent=round(ci, 3),
        problem_awareness=round(pa, 3),
        sample_queries=samples,
        notes="Intent estimated via LLM.",
    )


def _heuristic(keywords: tuple[Keyword, ...]) -> IntentResult:
    if not keywords:
        return IntentResult(0.0, 0.0, (), notes="No keywords to analyze.")
    buy_hits = problem_hits = 0
    samples: list[str] = []
    for kw in keywords:
        t = kw.term.lower()
        if any(m in t for m in _BUY_MARKERS):
            buy_hits += 1
            if len(samples) < 3:
                samples.append(kw.term)
        if any(m in t for m in _PROBLEM_MARKERS):
            problem_hits += 1
    n = len(keywords)
    return IntentResult(
        commercial_intent=round(buy_hits / n, 3),
        problem_awareness=round(problem_hits / n, 3),
        sample_queries=tuple(samples),
        notes="Intent estimated by keyword lexicon (offline fallback).",
    )
