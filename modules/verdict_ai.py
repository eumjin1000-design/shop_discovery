"""AI-written Go/No-Go verdict summary (quality tier — Claude Sonnet first).

The deterministic one-liner lives in :func:`modules.synthesizer._summary`; this
adds a richer, nuanced Korean paragraph when an LLM is available. Returns
``None`` offline so the caller can simply skip it.

Interface
---------
    ai_verdict_summary(verdict: Verdict) -> str | None
"""
from __future__ import annotations

from typing import Optional

from .llm import ask_text
from .models import Verdict


def ai_verdict_summary(verdict: Verdict) -> Optional[str]:
    scores = "; ".join(
        f"{line.name} {line.score:.0f}/{line.max_score:.0f}" for line in verdict.breakdown
    )
    prompt = (
        f'드랍쇼핑 신규 샵 후보 카테고리 "{verdict.category}"의 분석 결과를 한국어로 '
        "3~4문장으로 요약하라. "
        f"총점 {verdict.total_score:.0f}/100, 판정 {verdict.decision}. "
        f"항목별 점수 — {scores}. "
        "가장 강한 요인과 약한 요인을 짚고, 실행 관점의 권고(진입/보류/회피와 그 이유)를 "
        "균형 있게 담아라. 마크다운·불릿 없이 평문 문단으로만 작성."
    )
    return ask_text(prompt, tier="quality", max_tokens=400)
