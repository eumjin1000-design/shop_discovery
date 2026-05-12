"""Rendering helpers for the Shop Discovery Streamlit GUI (see app.py).

Kept separate from app.py so the page script stays small. Pure presentation:
no pipeline logic lives here.
"""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import streamlit as st

from modules import batch_report, report_gen, shop_namer, sourcing, sourcing_report
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
        use_container_width=True, hide_index=True,
    )


def excel_bytes(result: PipelineResult) -> tuple[str, bytes]:
    """Write the single-category report to ./output and return (name, bytes)."""
    path = report_gen.write_report(result)
    return Path(path).name, Path(path).read_bytes()


def render_batch(batch: list[tuple[str, PipelineResult]]) -> None:
    """Ranking table + top pick + Excel download for a 20-category batch run."""
    top_name, top_res = batch[0]
    tv = top_res.verdict
    st.success(
        f"🏆 **1위 추천: {top_name}** — {tv.total_score:.1f}/100 "
        f"({tv.decision}). 아래 입력창에 채워두었습니다."
    )
    rows = []
    for rank, (name, res) in enumerate(batch, start=1):
        v = res.verdict
        row = {"순위": rank, "카테고리": name, "총점": round(v.total_score, 1),
               "판정": v.decision}
        for line in v.breakdown:
            row[ko(line.name)] = round(line.score, 1)
        rows.append(row)
    styled = pd.DataFrame(rows).style.apply(
        lambda r: [_ROW_BG.get(r["판정"], "")] * len(r), axis=1
    )
    st.dataframe(styled, use_container_width=True, hide_index=True)

    path = batch_report.write_batch_report(batch)
    st.download_button(
        "⬇️ 전체 결과 Excel 다운로드", data=Path(path).read_bytes(),
        file_name=Path(path).name, key="batch_dl", use_container_width=True,
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


def _shop_name_block(category: str) -> None:
    st.markdown("**🏷️ 샵 이름 자동 생성** — 영어 · 기억하기 쉬움 · .com 가능성 고려")
    if st.button("🏷️ 샵 이름 5개 생성", key="gen_shop_names"):
        with st.spinner("샵 이름 생성 중..."):
            st.session_state["shop_names"] = shop_namer.generate_shop_names(category, 5)
        st.session_state["shop_names_cat"] = category
    names = (st.session_state.get("shop_names")
             if st.session_state.get("shop_names_cat") == category else None)
    if not names:
        return
    by = {sn.name: sn for sn in names}
    chosen = st.radio(
        "마음에 드는 이름 선택", [sn.name for sn in names], key="shop_name_radio",
        format_func=lambda n: f"{n}  —  {by[n].concept}  ·  🌐 {by[n].domain}",
    )
    st.session_state["shop_name_selected"] = chosen
    st.success(f"선택: **{chosen}**  ·  도메인 후보: `{by[chosen].domain}`")


def _sourcing_block(category: str) -> None:
    st.markdown(
        f"**📦 소싱 리스트 자동 생성** — {sourcing.TOTAL}개 "
        f"({sourcing.SUBCATS_N} 서브카테고리 × {sourcing.PRODUCTS_N} 상품 × {sourcing.VARIANTS_N} 변형)"
    )
    if st.button("📦 소싱 리스트 생성", key="gen_sourcing"):
        with st.spinner(f"{sourcing.TOTAL}개 상품 소싱 리스트 생성 중..."):
            items = sourcing.build_sourcing_list(category)
            path = sourcing_report.write_sourcing_report(
                category, items, shop_name=st.session_state.get("shop_name_selected"),
            )
        st.session_state["sourcing_items"] = items
        st.session_state["sourcing_path"] = path
        st.session_state["sourcing_cat"] = category
    items = (st.session_state.get("sourcing_items")
             if st.session_state.get("sourcing_cat") == category else None)
    if not items:
        return
    st.write(f"총 **{len(items)}개** 상품 — 미리보기 (상위 20개)")
    st.dataframe(
        [{"#": i + 1, "서브카테고리": it.subcategory, "상품명": it.product_name,
          "Amazon 검색 URL": it.amazon_url, "예상가격($)": it.est_price, "키워드": it.keyword}
         for i, it in enumerate(items[:20])],
        use_container_width=True, hide_index=True,
    )
    path = st.session_state["sourcing_path"]
    st.download_button(
        "⬇️ 소싱 리스트 Excel 다운로드", data=Path(path).read_bytes(),
        file_name=Path(path).name, key="sourcing_dl", use_container_width=True,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    st.caption(f"리포트는 `output/{Path(path).name}` 에도 저장되었습니다. (Amazon URL 은 셀 하이퍼링크)")


def render_go_tools(result: PipelineResult) -> None:
    """샵 이름 / 소싱 리스트 자동 생성 — GO 판정 카테고리에서만 노출."""
    st.subheader("🚀 다음 단계 (GO 전용)")
    category = result.request.category
    _shop_name_block(category)
    st.divider()
    _sourcing_block(category)
