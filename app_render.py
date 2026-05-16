"""Rendering helpers for the Shop Discovery Streamlit GUI (see app.py).

Kept separate from app.py so the page script stays small. Pure presentation:
no pipeline logic lives here.
"""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import streamlit as st

import app_go_tools
import app_spark_ui as spark_ui
from modules import batch_report, report_gen
from modules.models import PipelineResult

DECISION_COLOR = {"GO": "#2e7d32", "WATCH": "#f9a825", "NO-GO": "#c62828"}
DECISION_EMOJI = {"GO": "✅", "WATCH": "🟡", "NO-GO": "⛔"}

# Korean labels for the scorecard factor names produced by modules.synthesizer.
FACTOR_KO = {
    "Margin / unit economics": "마진/단위 경제성",
    "Search trend": "검색 트렌드",
    "Market & competition (BSR)": "시장 및 경쟁(BSR)",
    "Review opportunity": "리뷰 기회",
    "Purchase intent": "구매 의도",
}

_ROW_BG = {"GO": "background-color:#e6f4ea",
           "WATCH": "background-color:#fef7e0",
           "NO-GO": "background-color:#fce8e6"}

# Icon per scorecard factor (keyed by the Korean label).
FACTOR_ICON = {
    "마진/단위 경제성": "💰",
    "검색 트렌드": "📈",
    "시장 및 경쟁(BSR)": "🏪",
    "리뷰 기회": "⭐",
    "구매 의도": "🛒",
}


def ko(name: str) -> str:
    return FACTOR_KO.get(name, name)


def render_header(provider_label: str, llm_on: bool) -> None:
    """Left: 🐙 logo + subtitle. Right: Gemini+Claude (or mock) badge."""
    badge_bg, badge_fg, icon = (("#ede7f6", "#5e35b1", "🤖") if llm_on
                                else ("#f5f5f5", "#999999", "⚠️"))
    st.markdown(
        f"""
        <div style="display:flex;justify-content:space-between;align-items:center;
                    padding:4px 0 12px;border-bottom:1px solid #ececec;margin-bottom:16px">
          <div>
            <div style="font-size:30px;font-weight:800;line-height:1.1">🐙 샵 디스커버리</div>
            <div style="color:#777;font-size:13px;margin-top:3px">
              드랍쇼핑 신규 샵 발굴 자동화 — 카테고리 → Go/No-Go 판정 → Excel 리포트</div>
          </div>
          <div style="background:{badge_bg};color:{badge_fg};border-radius:18px;
                      padding:6px 14px;font-size:12.5px;font-weight:700;white-space:nowrap">
            {icon} {provider_label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_verdict_panel(verdict) -> None:
    """Gauge on the left; big score number + GO/WATCH badge on the right."""
    color = DECISION_COLOR.get(verdict.decision, "#555")
    emoji = DECISION_EMOJI.get(verdict.decision, "")
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:20px;border:1px solid #ececec;
                    border-radius:14px;padding:14px 20px;background:#fff">
          <div>{gauge_svg(verdict.total_score, verdict.decision)}</div>
          <div style="flex:1;text-align:right">
            <div style="font-size:62px;font-weight:900;color:{color};line-height:1">
              {verdict.total_score:.0f}<span style="font-size:22px;color:#bbb"> / 100</span></div>
            <div style="font-size:30px;font-weight:800;color:{color}">{emoji} {verdict.decision}</div>
            <div style="color:#999;font-size:12px;margin-top:4px">
              임계값: ≥70 GO · 50–69 WATCH · &lt;50 NO-GO</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def gauge_svg(score: float, decision: str) -> str:
    """Return an inline SVG semicircular gauge for a 0..100 score."""
    color = DECISION_COLOR.get(decision, "#555")
    angle = math.pi * (1 - score / 100.0)        # 0..100 -> 180..0 degrees
    cx, cy, r = 110, 110, 90
    x = cx + r * math.cos(angle)
    y = cy - r * math.sin(angle)
    return f"""
    <svg width="220" height="130" viewBox="0 0 220 130">
      <path d="M20 110 A90 90 0 0 1 200 110" fill="none"
            stroke="#e0e0e0" stroke-width="18" stroke-linecap="round"/>
      <path d="M20 110 A90 90 0 0 1 {x:.1f} {y:.1f}" fill="none"
            stroke="{color}" stroke-width="18" stroke-linecap="round"/>
      <text x="110" y="100" text-anchor="middle" font-size="34"
            font-weight="700" fill="{color}">{score:.0f}</text>
      <text x="110" y="122" text-anchor="middle" font-size="13" fill="#888">/ 100</text>
    </svg>
    """


def factor_bar(name: str, score: float, max_score: float, detail: str, icon: str | None = None) -> None:
    pct = score / max_score if max_score else 0.0
    hue = int(120 * pct)  # red -> green
    icon = icon or FACTOR_ICON.get(name, "•")
    st.markdown(
        f"""
        <div style="margin-bottom:10px">
          <div style="display:flex;justify-content:space-between;font-size:14px">
            <span><b>{icon} {name}</b></span><span>{score:.1f} / {max_score:.0f}</span>
          </div>
          <div style="background:#eee;border-radius:6px;height:14px;overflow:hidden">
            <div style="width:{pct*100:.1f}%;height:100%;background:hsl({hue},70%,45%)"></div>
          </div>
          <div style="font-size:12px;color:#777;margin-top:2px">{detail}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def scorecard_preview(result: PipelineResult) -> None:
    """st.dataframe preview of the 5 scorecard rows (shown above the download)."""
    st.markdown("**스코어카드 미리보기**")
    st.dataframe(
        [{"항목": ko(line.name), "점수": round(line.score, 1), "만점": line.max_score,
          "달성률": f"{(line.score / line.max_score * 100 if line.max_score else 0):.0f}%",
          "설명": line.detail} for line in result.verdict.breakdown],
        width="stretch", hide_index=True,
    )


def excel_bytes(result: PipelineResult) -> tuple[str, bytes]:
    """Write the single-category report to ./output and return (name, bytes)."""
    path = report_gen.write_report(result)
    return Path(path).name, Path(path).read_bytes()


def pipeline_rows(results: list[tuple[str, PipelineResult]]) -> list[dict]:
    """Convert pipeline results to the lightweight, JSON-serialisable row form
    used by :func:`render_batch` and persisted between runs.
    """
    return [
        {"name": name, "total": round(r.verdict.total_score, 1), "decision": r.verdict.decision,
         "breakdown": [[ko(l.name), round(l.score, 1), l.max_score] for l in r.verdict.breakdown],
         "summary": r.verdict.summary}
        for name, r in results
    ]


def render_batch(rows: list[dict]) -> None:
    """Ranking table + top pick + Excel download for batch results (row form)."""
    if not rows:
        return
    rows = sorted(rows, key=lambda r: r.get("total", 0), reverse=True)
    top = rows[0]
    st.success(
        f"🏆 **1위 추천: {top['name']}** — {top['total']:.1f}/100 "
        f"({top['decision']}). 아래 입력창에 채워두었습니다.  ·  누적 {len(rows)}개 분석됨"
    )
    table = []
    for rank, r in enumerate(rows, start=1):
        entry = {"순위": rank, "카테고리": r["name"], "총점": round(r["total"], 1), "판정": r["decision"]}
        for bn, sc, _mx in r["breakdown"]:
            entry[bn] = round(sc, 1)
        table.append(entry)
    styled = pd.DataFrame(table).style.apply(
        lambda x: [_ROW_BG.get(x["판정"], "")] * len(x), axis=1
    )
    st.dataframe(styled, width="stretch", hide_index=True)

    path = batch_report.write_batch_report(rows)
    st.download_button(
        "⬇️ 순위 결과 Excel 다운로드", data=Path(path).read_bytes(),
        file_name=Path(path).name, key="batch_dl", width="stretch",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    st.caption(f"리포트는 `output/{Path(path).name}` 에도 저장되었습니다.")


def render_strategy(result: PipelineResult) -> None:
    """'내 전략 기준' — heuristics tailored to an SEO / bulk-upload workflow."""
    total_volume = sum(k.est_monthly_volume for k in result.keywords)
    listings = result.bsr.competing_listings

    seo_ok = total_volume >= 8000 and listings < 12000
    bulk_ok = listings >= 1500   # enough product variety to scale a catalog

    # More problem-aware searches + more known complaints => more content angles.
    angle = result.intent.problem_awareness + min(len(result.review.top_complaints), 5) / 10.0
    blog = "쉬움" if angle >= 0.6 else ("보통" if angle >= 0.35 else "어려움")

    st.subheader("📌 내 전략 기준")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("SEO 적합도", "✅ 적합" if seo_ok else "❌ 부적합",
              help=f"월 검색량 합계 ~{total_volume:,} · 경쟁 리스팅 ~{listings:,}개 "
                   "— 검색량 ≥ 8,000 이고 경쟁 < 12,000 일 때 '적합'")
    c2.metric("대량 업로드 적합", "✅ 가능" if bulk_ok else "❌ 제한적",
              help=f"카테고리 내 경쟁 리스팅 ~{listings:,}개 — 상품 수 확장 여지 "
                   "(≥ 1,500 일 때 '가능')")
    c3.metric("블로그 콘텐츠 난이도", blog,
              help=f"문제 인지도 {result.intent.problem_awareness*100:.0f}% + 불만 테마 "
                   f"{len(result.review.top_complaints)}개 → 콘텐츠 소재 다양성 기준")
    c4.metric("영상 홍보 잠재력", "🔜 향후 적용",
              help="시각적 매력도 평가 — 추후 이미지/영상 분석 모듈 연동 예정")


def render_go_tools(result: PipelineResult) -> None:
    """샵 이름 / 소싱 리스트 자동 생성 — GO 판정 카테고리에서만 노출.
    Sourcing/shop-name blocks live in :mod:`app_go_tools` so this file
    stays under the 300-line hard limit."""
    st.subheader("🚀 다음 단계 (GO 전용)")
    category = result.request.category
    app_go_tools.render_go_tools_blocks(category)
    st.divider()
    spark_ui.render_spark_import_section(category)
