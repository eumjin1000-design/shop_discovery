"""Category catalog: the active list, AI-generated lists, analysis history,
and batch-result persistence. The seed list and the CuratedCategory model
live in :mod:`modules.curated_data`.
"""
from __future__ import annotations

import json
import os
import random
from dataclasses import asdict

from .curated_data import CURATED, CuratedCategory  # re-exported for callers
from .llm import ask_json

_DATA_DIR = os.path.dirname(os.path.dirname(__file__))
_GEN_FILE = os.path.join(_DATA_DIR, "generated_categories.json")
_HISTORY_FILE = os.path.join(_DATA_DIR, "analysis_history.json")
_GEN_BAK = os.path.join(_DATA_DIR, "generated_categories.bak.json")
_HISTORY_BAK = os.path.join(_DATA_DIR, "analysis_history.bak.json")
_BATCH_FILE = os.path.join(_DATA_DIR, "batch_results.json")


# --------------------------------------------------------------------------
# Persistence: AI-generated categories + analysis history
# --------------------------------------------------------------------------
def _read_json(path: str, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def _coerce(item: dict) -> CuratedCategory | None:
    if not isinstance(item, dict) or not str(item.get("name", "")).strip():
        return None

    def rate(v) -> int:
        try:
            return max(1, min(3, int(v)))
        except (TypeError, ValueError):
            return 2

    return CuratedCategory(
        name=str(item["name"]).strip(),
        margin=rate(item.get("margin")),
        demand=rate(item.get("demand")),
        competition=rate(item.get("competition")),
        reason=str(item.get("reason", "")).strip() or "AI 추천 트렌딩 카테고리.",
        age=str(item.get("age", "")).strip()[:20],
    )


def load_generated() -> list[CuratedCategory]:
    out: list[CuratedCategory] = []
    for item in _read_json(_GEN_FILE, []):
        cat = _coerce(item)
        if cat is not None:
            out.append(cat)
    return out


def _history_raw() -> dict[str, str | None]:
    """Return ``{category_name: decision_or_None}``; tolerates the legacy list format."""
    data = _read_json(_HISTORY_FILE, {})
    if isinstance(data, list):
        return {str(n).strip(): None for n in data if str(n).strip()}
    if isinstance(data, dict):
        return {str(k).strip(): (str(v) if v else None)
                for k, v in data.items() if str(k).strip()}
    return {}


def load_history() -> set[str]:
    return set(_history_raw())


def load_history_map() -> dict[str, str | None]:
    return _history_raw()


def mark_analyzed(*category_names: str, decision: str | None = None) -> None:
    hist = _history_raw()
    for n in category_names:
        n = n.strip()
        if n:
            hist[n] = decision or hist.get(n)
    _write_json(_HISTORY_FILE, hist)


def record_decisions(mapping: dict[str, str | None]) -> None:
    hist = _history_raw()
    for name, decision in mapping.items():
        name = str(name).strip()
        if name:
            hist[name] = decision or hist.get(name)
    _write_json(_HISTORY_FILE, hist)


def _backup_state() -> None:
    for src, dst in ((_GEN_FILE, _GEN_BAK), (_HISTORY_FILE, _HISTORY_BAK)):
        data = _read_json(src, None)
        if data is not None:
            _write_json(dst, data)


def restore_previous_list() -> bool:
    """Swap the generated list + history back to the last backup. False if none."""
    gen_bak = _read_json(_GEN_BAK, None)
    if gen_bak is None:
        return False
    _write_json(_GEN_FILE, gen_bak)
    hist_bak = _read_json(_HISTORY_BAK, None)
    _write_json(_HISTORY_FILE, hist_bak if hist_bak is not None else {})
    clear_batch_results()
    return True


def has_backup() -> bool:
    return _read_json(_GEN_BAK, None) is not None


# --------------------------------------------------------------------------
# Full-state export / import — survives Streamlit Cloud REDEPLOYS.
# The per-feature JSON files are gitignored, so a fresh Cloud container can
# lose them on a new deploy. export_all_state() bundles everything into one
# JSON the user downloads; import_all_state() restores it after any update.
# --------------------------------------------------------------------------
def export_all_state() -> dict:
    """Bundle every persisted file into one JSON-serialisable dict."""
    import time
    return {
        "version": 1,
        "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "generated_categories": _read_json(_GEN_FILE, None),
        "analysis_history": _read_json(_HISTORY_FILE, None),
        "batch_results": _read_json(_BATCH_FILE, None),
        "generated_categories_bak": _read_json(_GEN_BAK, None),
        "analysis_history_bak": _read_json(_HISTORY_BAK, None),
    }


def import_all_state(data: dict) -> bool:
    """Restore every file from an export_all_state() bundle. False if invalid."""
    if not isinstance(data, dict) or "version" not in data:
        return False
    mapping = {
        "generated_categories": _GEN_FILE,
        "analysis_history": _HISTORY_FILE,
        "batch_results": _BATCH_FILE,
        "generated_categories_bak": _GEN_BAK,
        "analysis_history_bak": _HISTORY_BAK,
    }
    wrote = False
    for key, path in mapping.items():
        value = data.get(key)
        if value is not None:
            _write_json(path, value)
            wrote = True
    return wrote


# --------------------------------------------------------------------------
# Batch ranking results — persisted so partial runs survive an app restart
# --------------------------------------------------------------------------
def save_batch_results(rows: list[dict]) -> None:
    _write_json(_BATCH_FILE, list(rows))


def load_batch_results() -> list[dict]:
    data = _read_json(_BATCH_FILE, [])
    return data if isinstance(data, list) else []


def clear_batch_results() -> None:
    try:
        os.remove(_BATCH_FILE)
    except OSError:
        pass


MAX_CATEGORIES = 20


def all_categories() -> tuple[CuratedCategory, ...]:
    """The active category list (at most :data:`MAX_CATEGORIES`).

    If ``generated_categories.json`` exists with usable entries (i.e. an "AI
    새목록" has been generated), return *only* those — the seed CURATED list is
    not merged in. Otherwise fall back to the seed CURATED list.
    """
    generated = load_generated()
    if generated:
        active = generated
    else:
        active = list(CURATED)
    # dedupe by lowercased name, keep order, cap at MAX_CATEGORIES
    seen: set[str] = set()
    out: list[CuratedCategory] = []
    for cat in active:
        key = cat.name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(cat)
        if len(out) >= MAX_CATEGORIES:
            break
    return tuple(out)


def names() -> list[str]:
    return [c.name for c in all_categories()]


def by_name(name: str) -> CuratedCategory | None:
    for c in all_categories():
        if c.name == name:
            return c
    return None


def random_category() -> CuratedCategory:
    return random.choice(all_categories())


def generate_new_categories(n: int = 20, replace: bool = False,
                            target_age: str = "") -> list[CuratedCategory]:
    """Ask the AI for `n` trending dropshipping categories not used before.

    ``replace=True`` (the "AI 새목록" action): back up the current generated
    list + analysis history, then replace the generated list with the fresh
    ones and clear the history. ``replace=False``: append to the existing list
    (deduped). Returns ``[]`` if the API is unavailable or returns nothing.

    ``target_age`` (e.g. ``"40-60"``): when non-empty, instruct the LLM to
    prioritise niches whose primary US buyers fall in that age range — and
    populate each result's ``age`` field. Empty = no age filter.
    """
    exclude = ({c.name.lower() for c in CURATED}
               | {c.name.lower() for c in all_categories()}
               | {h.lower() for h in load_history()})
    age_clause = (
        f"\nFOCUS: categories whose primary US buyer age range falls within "
        f"**{target_age}**. Examples for 40-60: orthopedic supports, "
        "gardening tools, premium kitchen, golf accessories, hair growth, "
        "joint supplements. Avoid Gen-Z-only niches.\n"
        if target_age else ""
    )
    prompt = (
        "You are a dropshipping market analyst. List "
        f"{n} CURRENTLY TRENDING dropshipping product categories suitable for a "
        "brand-new store. Do NOT include any of these already-used categories "
        f"(case-insensitive): {sorted(exclude)}." + age_clause + " For each "
        "category rate `margin`, `demand`, `competition` on a 1-3 scale where "
        "3 is most favorable (competition: 3 = least crowded). Give a "
        "one-line Korean `reason` referencing margin/demand/competition. "
        'Also include `age` (e.g. "25-34" or "40-60") — primary US buyer age. '
        "Return ONLY a JSON array: "
        '[{"name": "<English>", "margin": 1-3, "demand": 1-3, '
        '"competition": 1-3, "reason": "<Korean>", "age": "<range>"}]. No prose.'
    )
    data = ask_json(prompt, max_tokens=2048)
    if not isinstance(data, list):
        return []

    fresh: list[CuratedCategory] = []
    seen = set(exclude)
    for item in data:
        cat = _coerce(item)
        if cat is None or cat.name.lower() in seen:
            continue
        seen.add(cat.name.lower())
        fresh.append(cat)
        if len(fresh) >= n:
            break
    if not fresh:
        return []

    if replace:
        _backup_state()
        _write_json(_GEN_FILE, [asdict(c) for c in fresh])
        _write_json(_HISTORY_FILE, {})       # reset analysis history
        clear_batch_results()                # stale ranking refers to old list
        return fresh

    combined = load_generated() + fresh
    deduped: list[CuratedCategory] = []
    seen_keys: set[str] = {c.name.lower() for c in CURATED}
    for cat in combined:
        if cat.name.lower() in seen_keys:
            continue
        seen_keys.add(cat.name.lower())
        deduped.append(cat)
    _write_json(_GEN_FILE, [asdict(c) for c in deduped])
    return deduped
