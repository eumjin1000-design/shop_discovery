"""Curated list of dropshipping-friendly categories for the GUI.

Each entry is rated 1-3 on three axes where 3 is most favorable:
    margin       - typical net margin headroom (sourcing-to-retail markup)
    demand       - search volume / market size
    competition  - 3 = uncrowded, 1 = highly saturated

``reason`` is a one-line Korean rationale referencing those axes — used as the
tooltip / caption next to each category in the UI.
"""
from __future__ import annotations

import json
import os
import random
from dataclasses import asdict, dataclass

from .llm import ask_json

_DATA_DIR = os.path.dirname(os.path.dirname(__file__))
_GEN_FILE = os.path.join(_DATA_DIR, "generated_categories.json")
_HISTORY_FILE = os.path.join(_DATA_DIR, "analysis_history.json")
_GEN_BAK = os.path.join(_DATA_DIR, "generated_categories.bak.json")
_HISTORY_BAK = os.path.join(_DATA_DIR, "analysis_history.bak.json")


@dataclass(frozen=True)
class CuratedCategory:
    name: str
    margin: int        # 1..3
    demand: int        # 1..3
    competition: int   # 1..3 (higher == less crowded)
    reason: str

    def stars(self) -> str:
        def s(n: int) -> str:
            return "★" * n + "☆" * (3 - n)
        return f"마진 {s(self.margin)} · 수요 {s(self.demand)} · 경쟁여유 {s(self.competition)}"

    def label(self) -> str:
        return f"{self.name}  —  {self.stars()}"


CURATED: tuple[CuratedCategory, ...] = (
    CuratedCategory("Pet supplies (automatic feeder, slow-feeder bowl)", 3, 3, 2,
                    "반려동물 시장 수요가 꾸준히 성장, 객단가 대비 소싱가 낮아 마진 여유 큼. 경쟁은 중간."),
    CuratedCategory("Posture corrector / back support", 3, 2, 2,
                    "원가 대비 2~4배 마크업 가능, 재택근무 확산으로 수요 안정. 경쟁 중간."),
    CuratedCategory("Car accessories (organizer, phone mount)", 3, 3, 2,
                    "소형·경량으로 배송비 부담 적어 마진 우수, 검색량 풍부. 경쟁은 중간."),
    CuratedCategory("Kitchen gadgets (multi-tools, storage)", 2, 3, 2,
                    "검색량 매우 높고 충동구매 잘 발생. 다만 노출 경쟁이 치열해 마진 압박 있음."),
    CuratedCategory("Home fitness gear (resistance bands, foam roller)", 3, 2, 2,
                    "초저가 소싱 + 높은 마크업으로 마진 최상위권. 수요는 계절성 있음, 경쟁 중간."),
    CuratedCategory("LED / ambient lighting (strips, mood lamps)", 3, 3, 2,
                    "트렌드 상승 + 객단가 대비 원가 낮음. 경쟁은 늘고 있으나 차별화 여지 있음."),
    CuratedCategory("Phone accessories (cases, grips, stands)", 3, 3, 1,
                    "수요·마진 모두 최상이나 경쟁이 극심 — 디자인/번들로 차별화 필수."),
    CuratedCategory("Baby & toddler safety products", 3, 2, 3,
                    "안전 관련이라 가격 민감도 낮아 마진 우수, 경쟁도 비교적 낮음. 수요는 틈새."),
    CuratedCategory("Skincare tools (gua sha, LED mask, roller)", 3, 3, 2,
                    "뷰티 트렌드로 수요 급증, 마크업 여력 큼. 경쟁 증가 중이라 브랜딩 중요."),
    CuratedCategory("Outdoor & camping gear (compact)", 2, 2, 3,
                    "캠핑 인구 증가로 경쟁 아직 여유, 다만 부피·무게로 배송비가 마진 갉아먹음."),
    CuratedCategory("Eco / reusable products (silicone bags, bottles)", 3, 2, 2,
                    "친환경 트렌드 + 낮은 원가로 마진 좋음. 수요는 틈새, 경쟁 중간."),
    CuratedCategory("Minimalist jewelry & accessories", 3, 3, 1,
                    "원가 대비 마크업 매우 큼, 수요 풍부. 경쟁 포화 — 디자인 독창성이 관건."),
    CuratedCategory("Phone photography accessories (ring light, mini gimbal)", 2, 2, 3,
                    "콘텐츠 크리에이터 수요 신규 형성, 경쟁 여유. 마진은 중간 수준."),
    CuratedCategory("Sleep aids (eye mask, white-noise machine)", 3, 2, 3,
                    "건강·웰빙 키워드로 가격 저항 낮아 마진 우수, 경쟁도 낮음. 수요는 틈새."),
    CuratedCategory("Desk organizers / WFH accessories", 3, 2, 2,
                    "재택근무 정착으로 안정 수요, 소형이라 마진 좋음. 경쟁 중간."),
    CuratedCategory("Travel accessories (packing cubes, adapters)", 3, 2, 2,
                    "여행 회복세 + 번들 판매로 객단가 상승, 마진 양호. 경쟁 중간."),
    CuratedCategory("Montessori / educational toys", 3, 2, 2,
                    "부모 지갑이 잘 열려 마진 우수, 검색량은 틈새. 경쟁 중간."),
    CuratedCategory("Compact smart-home gadgets", 2, 3, 2,
                    "스마트홈 키워드 검색량 큼. 마진은 부품가로 중간, 경쟁 중간."),
    CuratedCategory("Indoor garden / plant care", 3, 2, 3,
                    "플랜테리어 트렌드로 경쟁 여유, 소품 위주라 마진 좋음. 수요는 틈새."),
    CuratedCategory("Hair tools & accessories", 3, 3, 1,
                    "수요·마진 모두 우수하나 경쟁 포화 — 차별화된 키워드 공략 필요."),
)


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
    return True


def has_backup() -> bool:
    return _read_json(_GEN_BAK, None) is not None


def all_categories() -> tuple[CuratedCategory, ...]:
    """Seed categories first, then AI-generated ones, deduped by lowercased name."""
    seen: set[str] = set()
    out: list[CuratedCategory] = []
    for cat in (*CURATED, *load_generated()):
        key = cat.name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(cat)
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


def generate_new_categories(n: int = 20, replace: bool = False) -> list[CuratedCategory]:
    """Ask the AI for `n` trending dropshipping categories not used before.

    ``replace=True`` (the "AI 새목록" action): back up the current generated
    list + analysis history, then replace the generated list with the fresh
    ones and clear the history. ``replace=False``: append to the existing list
    (deduped). Returns ``[]`` if the API is unavailable or returns nothing.
    """
    exclude = {c.name.lower() for c in all_categories()} | {h.lower() for h in load_history()}
    prompt = (
        "You are a dropshipping market analyst. List "
        f"{n} CURRENTLY TRENDING dropshipping product categories suitable for a "
        "brand-new store. Do NOT include any of these already-used categories "
        f"(case-insensitive): {sorted(exclude)}. For each category rate "
        "`margin`, `demand`, `competition` on a 1-3 scale where 3 is most "
        "favorable (competition: 3 = least crowded). Give a one-line Korean "
        "`reason` referencing margin/demand/competition. Return ONLY a JSON "
        'array: [{"name": "<English>", "margin": 1-3, "demand": 1-3, '
        '"competition": 1-3, "reason": "<Korean>"}]. No prose.'
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
