"""Seed list of dropshipping-friendly categories + the CuratedCategory model.

Each entry is rated 1-3 on three *intrinsic product* axes (3 is best):
    perceived_value    - how much value the buyer perceives vs. unit cost
                         (premium feel, low price resistance)
    problem_solving    - how clearly the product solves a concrete problem
    niche_specificity  - how tight/specific the micro-niche is
                         (3 = sharp 3-depth niche, 1 = broad commodity)

``reason`` is a one-line Korean rationale shown as the caption next to each
category in the UI.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CuratedCategory:
    name: str
    perceived_value: int    # 1..3
    problem_solving: int     # 1..3
    niche_specificity: int   # 1..3 (higher == tighter micro-niche)
    reason: str
    age: str = ""      # primary buyer age range, e.g. "25-34" or "40-60"

    def stars(self) -> str:
        def s(n: int) -> str:
            n = max(0, min(3, int(n or 0)))
            return "★" * n + "☆" * (3 - n)
        return (f"가치 {s(self.perceived_value)} · 해결 {s(self.problem_solving)} "
                f"· 틈새 {s(self.niche_specificity)}")

    def label(self) -> str:
        suffix = f" · {self.age}" if self.age else ""
        return f"{self.name}  —  {self.stars()}{suffix}"


CURATED: tuple[CuratedCategory, ...] = (
    CuratedCategory("Pet supplies (automatic feeder, slow-feeder bowl)", 2, 3, 2,
                    "반려동물 시장 수요가 꾸준히 성장, 객단가 대비 소싱가 낮아 마진 여유 큼. 경쟁은 중간."),
    CuratedCategory("Posture corrector / back support", 3, 3, 3,
                    "원가 대비 2~4배 마크업 가능, 재택근무 확산으로 수요 안정. 경쟁 중간."),
    CuratedCategory("Car accessories (organizer, phone mount)", 2, 2, 2,
                    "소형·경량으로 배송비 부담 적어 마진 우수, 검색량 풍부. 경쟁은 중간."),
    CuratedCategory("Kitchen gadgets (multi-tools, storage)", 1, 2, 1,
                    "검색량 매우 높고 충동구매 잘 발생. 다만 노출 경쟁이 치열해 마진 압박 있음."),
    CuratedCategory("Home fitness gear (resistance bands, foam roller)", 2, 2, 2,
                    "초저가 소싱 + 높은 마크업으로 마진 최상위권. 수요는 계절성 있음, 경쟁 중간."),
    CuratedCategory("LED / ambient lighting (strips, mood lamps)", 2, 1, 2,
                    "트렌드 상승 + 객단가 대비 원가 낮음. 경쟁은 늘고 있으나 차별화 여지 있음."),
    CuratedCategory("Phone accessories (cases, grips, stands)", 1, 1, 1,
                    "수요·마진 모두 최상이나 경쟁이 극심 — 디자인/번들로 차별화 필수."),
    CuratedCategory("Baby & toddler safety products", 3, 3, 2,
                    "안전 관련이라 가격 민감도 낮아 마진 우수, 경쟁도 비교적 낮음. 수요는 틈새."),
    CuratedCategory("Skincare tools (gua sha, LED mask, roller)", 3, 2, 2,
                    "뷰티 트렌드로 수요 급증, 마크업 여력 큼. 경쟁 증가 중이라 브랜딩 중요."),
    CuratedCategory("Outdoor & camping gear (compact)", 2, 2, 1,
                    "캠핑 인구 증가로 경쟁 아직 여유, 다만 부피·무게로 배송비가 마진 갉아먹음."),
    CuratedCategory("Eco / reusable products (silicone bags, bottles)", 2, 2, 2,
                    "친환경 트렌드 + 낮은 원가로 마진 좋음. 수요는 틈새, 경쟁 중간."),
    CuratedCategory("Minimalist jewelry & accessories", 3, 1, 2,
                    "원가 대비 마크업 매우 큼, 수요 풍부. 경쟁 포화 — 디자인 독창성이 관건."),
    CuratedCategory("Phone photography accessories (ring light, mini gimbal)", 2, 2, 3,
                    "콘텐츠 크리에이터 수요 신규 형성, 경쟁 여유. 마진은 중간 수준."),
    CuratedCategory("Sleep aids (eye mask, white-noise machine)", 3, 3, 3,
                    "건강·웰빙 키워드로 가격 저항 낮아 마진 우수, 경쟁도 낮음. 수요는 틈새."),
    CuratedCategory("Desk organizers / WFH accessories", 2, 2, 2,
                    "재택근무 정착으로 안정 수요, 소형이라 마진 좋음. 경쟁 중간."),
    CuratedCategory("Travel accessories (packing cubes, adapters)", 2, 2, 2,
                    "여행 회복세 + 번들 판매로 객단가 상승, 마진 양호. 경쟁 중간."),
    CuratedCategory("Montessori / educational toys", 3, 2, 3,
                    "부모 지갑이 잘 열려 마진 우수, 검색량은 틈새. 경쟁 중간."),
    CuratedCategory("Compact smart-home gadgets", 2, 2, 2,
                    "스마트홈 키워드 검색량 큼. 마진은 부품가로 중간, 경쟁 중간."),
    CuratedCategory("Indoor garden / plant care", 2, 2, 2,
                    "플랜테리어 트렌드로 경쟁 여유, 소품 위주라 마진 좋음. 수요는 틈새."),
    CuratedCategory("Hair tools & accessories", 2, 1, 1,
                    "수요·마진 모두 우수하나 경쟁 포화 — 차별화된 키워드 공략 필요."),
)
