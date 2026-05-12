"""Streamlit GUI for Shop Discovery.

Run with:
    streamlit run app.py

Provides a category input, a "분석 실행" button, a score gauge + per-factor
bar breakdown, the Go / No-Go verdict, and an Excel download button. The
pipeline itself lives in main.run_pipeline; this file is presentation only.
"""
from __future__ import annotations

import io
from pathlib import Path

import streamlit as st

# Load .env so ANTHROPIC_API_KEY is available (optional dependency).
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).with_name(".env"))
except ImportError:
    pass

from main import run_pipeline
from modules import report_gen
from modules.llm import is_available
from modules.models import PipelineResult

DECISION_COLOR = {"GO": "#2e7d32", "WATCH": "#f9a825", "NO-GO": "#c62828"}
DECISION_EMOJI = {"GO": "✅", "WATCH": "🟡", "NO-GO": "⛔"}


# --------------------------------------------------------------------------
# Rendering helpers
# --------------------------------------------------------------------------
def _gauge(score: float, decision: str) -> str:
    """Return an inline SVG semicircular gauge for a 0..100 score."""
    color = DECISION_COLOR.get(decision, "#555")
    # Map 0..100 -> 180..0 degrees (left to right along the top half).
    import math

    angle = math.pi * (1 - score / 100.0)
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
      <text x="110" y="122" text-anchor="middle" font-size="13"
            fill="#888">/ 100</text>
    </svg>
    """


def _factor_bar(name: str, score: float, max_score: float, detail: str) -> None:
    pct = score / max_score if max_score else 0.0
    hue = int(120 * pct)  # red -> green
    st.markdown(
        f"""
        <div style="margin-bottom:10px">
          <div style="display:flex;justify-content:space-between;font-size:14px">
            <span><b>{name}</b></span>
            <span>{score:.1f} / {max_score:.0f}</span>
          </div>
          <div style="background:#eee;border-radius:6px;height:14px;overflow:hidden">
            <div style="width:{pct*100:.1f}%;height:100%;
                        background:hsl({hue},70%,45%)"></div>
          </div>
          <div style="font-size:12px;color:#777;margin-top:2px">{detail}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _build_excel_bytes(result: PipelineResult) -> tuple[str, bytes]:
    """Write the report to ./output and also return it as in-memory bytes."""
    path = report_gen.write_report(result)
    data = Path(path).read_bytes()
    return Path(path).name, data


# --------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------
st.set_page_config(page_title="Shop Discovery", page_icon="🐙", layout="centered")
st.title("🐙 Shop Discovery")
st.caption("드랍쇼핑 신규 샵 발굴 자동화 — 카테고리 입력 → Go/No-Go 판정 → Excel 리포트")

if not is_available():
    st.info(
        "ANTHROPIC_API_KEY 가 설정되지 않아 데이터 모듈이 결정론적 mock 으로 동작합니다. "
        "(같은 카테고리는 항상 같은 결과) — 실데이터 연동 전까지 의사결정 참고용으로만 사용하세요.",
        icon="ℹ️",
    )

with st.form("discovery"):
    category = st.text_input("분석할 카테고리", placeholder="예: wireless earbuds, cat water fountain")
    col_a, col_b = st.columns(2)
    market = col_a.text_input("타겟 시장", value="US")
    currency = col_b.text_input("통화", value="USD")
    submitted = st.form_submit_button("🔍 분석 실행", use_container_width=True)

if submitted:
    if not category.strip():
        st.warning("카테고리를 입력하세요.")
        st.stop()
    with st.spinner(f'"{category}" 분석 중...'):
        result = run_pipeline(category.strip(), target_market=market.strip() or "US",
                              currency=currency.strip() or "USD")
    st.session_state["result"] = result

result: PipelineResult | None = st.session_state.get("result")
if result is not None:
    v = result.verdict
    color = DECISION_COLOR.get(v.decision, "#555")
    emoji = DECISION_EMOJI.get(v.decision, "")

    st.divider()
    g_col, d_col = st.columns([1, 1.3])
    with g_col:
        st.markdown(_gauge(v.total_score, v.decision), unsafe_allow_html=True)
    with d_col:
        st.markdown(
            f"<div style='font-size:40px;font-weight:800;color:{color}'>"
            f"{emoji} {v.decision}</div>"
            f"<div style='color:#666'>총점 {v.total_score:.1f} / 100 "
            f"&nbsp;|&nbsp; 임계값: ≥70 GO · 50–69 WATCH · &lt;50 NO-GO</div>",
            unsafe_allow_html=True,
        )
    st.write(v.summary)

    st.subheader("스코어카드 (100점)")
    for line in v.breakdown:
        _factor_bar(line.name, line.score, line.max_score, line.detail)

    with st.expander("키워드"):
        st.dataframe(
            [{"키워드": k.term, "월 검색량(추정)": k.est_monthly_volume or "n/a",
              "근거": k.rationale} for k in result.keywords],
            use_container_width=True, hide_index=True,
        )

    with st.expander("모듈별 상세 지표"):
        t, b, rv, it, mg = result.trend, result.bsr, result.review, result.intent, result.margin
        st.markdown(f"**Trend** — {t.notes}")
        st.markdown(f"**Amazon BSR** — {b.notes}")
        st.markdown(f"**Reviews** — {rv.notes}  \n불만 테마: {', '.join(rv.top_complaints) or 'n/a'}")
        st.markdown(f"**Intent** — {it.notes}  \n예시 쿼리: {', '.join(it.sample_queries) or 'n/a'}")
        st.markdown(f"**Margin** — {mg.notes}")

    fname, data = _build_excel_bytes(result)
    st.download_button(
        "⬇️ Excel 리포트 다운로드", data=data, file_name=fname,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    st.caption(f"리포트는 `output/{fname}` 에도 저장되었습니다.")
