"""English category name → Korean translation with persistent cache.

Used by the batch ranking UI/Excel to show Korean labels alongside the
canonical English category names. Translations come from:

  1. Built-in dictionary (instant, deterministic) — covers the seed CURATED
     list and common AI-generated drop-shipping niches.
  2. LLM fallback (Claude/Gemini, ~1 second per new category) for entries
     not in the dictionary.
  3. JSON cache (``category_ko_cache.json``) — every new translation is
     persisted so the LLM is called at most once per category, ever.

If both dict and LLM lookups fail, the original English name is returned
so the UI never breaks.
"""
from __future__ import annotations

import json
import os
import re

from .llm import ask_text

_CACHE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "category_ko_cache.json"
)

# Built-in dict covers all 20 CURATED seed names + the 20 visible in the
# user's latest batch run. Keys are the English category names exactly as
# stored; values are concise Korean labels (no punctuation, ~10 chars).
_DICT: dict[str, str] = {
    # --- Seed CURATED 20 ---
    "Pet supplies (automatic feeder, slow-feeder bowl)": "반려동물 용품",
    "Posture corrector / back support": "자세 교정기 / 허리 지지대",
    "Car accessories (organizer, phone mount)": "차량 액세서리",
    "Kitchen gadgets (multi-tools, storage)": "주방용품",
    "Home fitness gear (resistance bands, foam roller)": "홈 피트니스 장비",
    "LED / ambient lighting (strips, mood lamps)": "LED / 무드등",
    "Phone accessories (cases, grips, stands)": "휴대폰 액세서리",
    "Baby & toddler safety products": "유아 안전용품",
    "Skincare tools (gua sha, LED mask, roller)": "스킨케어 도구",
    "Outdoor & camping gear (compact)": "아웃도어 / 캠핑 장비",
    "Eco / reusable products (silicone bags, bottles)": "친환경 재사용 제품",
    "Minimalist jewelry & accessories": "미니멀 주얼리",
    "Phone photography accessories (ring light, mini gimbal)": "휴대폰 촬영 액세서리",
    "Sleep aids (eye mask, white-noise machine)": "수면 보조용품",
    "Desk organizers / WFH accessories": "데스크 정리 / 재택근무 용품",
    "Travel accessories (packing cubes, adapters)": "여행 액세서리",
    "Montessori / educational toys": "몬테소리 / 교육 완구",
    "Compact smart-home gadgets": "스마트홈 가젯",
    "Indoor garden / plant care": "실내 정원 / 식물 관리",
    "Hair tools & accessories": "헤어 도구 / 액세서리",
    # --- Recent AI-generated batch (40-60 target age) ---
    "Fishing Gear & Accessories": "낚시 장비 / 액세서리",
    "Memory Foam & Orthopedic Pillows": "메모리폼 / 정형외과 베개",
    "Blood Pressure & Health Monitoring Gadgets": "혈압 / 건강 모니터링 기기",
    "Portable Massagers & Percussion Therapy": "휴대용 마사지기 / 진동 치료기",
    "Ergonomic Kitchen Tools for Arthritis": "관절염용 주방 도구",
    "Golf Training Aids & Accessories": "골프 트레이닝 / 액세서리",
    "Anti-Snoring Devices & Sleep Positioning Aids": "코골이 방지 / 수면 자세 보조",
    "Pill Organizers & Medication Management": "약통 / 복약 관리",
    "Menopause & Hormone Balance Supplements": "갱년기 / 호르몬 보충제",
    "Premium Gardening Tools & Kneelers": "프리미엄 원예 도구 / 무릎 보호대",
    "Woodworking & DIY Hobby Tools": "목공 / DIY 취미 도구",
    "Heating Pads & Infrared Therapy Devices": "온열 패드 / 적외선 치료기",
    "Reading Glasses & Blue Light Blocking Glasses": "돋보기 / 블루라이트 차단 안경",
    "Wine Accessories & Preservation Tools": "와인 액세서리 / 보존 도구",
    "Joint & Mobility Support Braces": "관절 / 보행 보조 브레이스",
    "Anti-Aging Supplement Bundles (Collagen, NMN)": "안티에이징 보충제 번들",
    "Compression Socks & Circulation Wear": "압박 스타킹 / 혈액 순환 의류",
    "Hair Regrowth & Scalp Care Devices": "발모 / 두피 케어 기기",
    "Hearing Amplifiers & Ear Health Devices": "보청기 / 귀 건강 기기",
    "Orthopedic Shoe Insoles & Foot Care": "정형외과 깔창 / 발 관리",
}


def _load_cache() -> dict[str, str]:
    try:
        with open(_CACHE_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_cache(cache: dict[str, str]) -> None:
    try:
        with open(_CACHE_FILE, "w", encoding="utf-8") as fh:
            json.dump(cache, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass


def _strip_annotation(name: str) -> str:
    return re.sub(r"\s*\([^)]*\)", "", name or "").strip()


def _ask_llm(name: str) -> str | None:
    """Single-shot Korean translation. ~50-100 tokens, ~1 sec."""
    prompt = (
        f'Translate this English drop-shipping product category name to '
        f'concise Korean (5-15 chars, no parentheses, no punctuation at '
        f'the end). Return ONLY the Korean translation, nothing else.\n\n'
        f'Category: "{name}"\n\nKorean:'
    )
    try:
        text = ask_text(prompt, max_tokens=80)
    except Exception:
        return None
    if not text:
        return None
    # Strip quotes, prefixes like "Korean:", excess whitespace
    text = text.strip().strip('"').strip("'")
    text = re.sub(r"^(?:Korean|한국어|번역)\s*[:\-]\s*", "", text).strip()
    # Drop anything after the first newline
    text = text.split("\n", 1)[0].strip()
    return text or None


def translate(name: str) -> str:
    """English category → Korean. Returns the English name on failure."""
    if not name:
        return ""
    # Exact match first
    if name in _DICT:
        return _DICT[name]
    # Annotation-stripped match
    stripped = _strip_annotation(name)
    if stripped in _DICT:
        return _DICT[stripped]
    # Cache lookup
    cache = _load_cache()
    if name in cache:
        return cache[name]
    # LLM fallback
    ko = _ask_llm(name)
    if ko:
        cache[name] = ko
        _save_cache(cache)
        return ko
    return name


def translate_many(names: list[str]) -> dict[str, str]:
    """Bulk translate. Same fallback chain, persists every new hit."""
    return {n: translate(n) for n in names}
