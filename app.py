"""Streamlit GUI for Shop Discovery.

Run with:
    streamlit run app.py

Category selection via a clickable card grid (emoji + stars + GO/WATCH badge),
list-management buttons, summary stat cards, single-category analysis with a
score gauge / scorecard / Excel / sourcing tools, a batch "전체 자동 분석" run,
and a "📌 내 전략 기준" panel. Rendering lives in app_render.py and
app_catalog_ui.py; the pipeline lives in main.run_pipeline.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

# Load .env so ANTHROPIC_API_KEY is available (optional dependency).
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).with_name(".env"))
except ImportError:
    pass

import app_catalog_ui as catalog
import app_render as ui
from main import run_all_curated, run_pipeline
from modules import categories, llm, verdict_ai
from modules.models import PipelineResult

# --------------------------------------------------------------------------
st.set_page_config(page_title="Shop Discovery", page_icon="🐙", layout="centered")
st.title("🐙 Shop Discovery")
st.caption("드랍쇼핑 신규 샵 발굴 자동화 — 카테고리 입력 → Go/No-Go 판정 → Excel 리포트")

if llm.any_available():
    st.caption(
        f"🤖 LLM: **{llm.provider_label()}** — 대량 작업은 Gemini Flash(무료), "
        "샵 이름·판정 요약은 Claude Sonnet 우선 (없으면 상호 폴백)"
    )
else:
    st.info(
        "LLM API 키가 없어 데이터 모듈이 결정론적 mock 으로 동작합니다. "
        "(.env 의 GOOGLE_API_KEY / ANTHROPIC_API_KEY 설정 후 재시작) "
        "— 같은 카테고리는 항상 같은 결과, 의사결정 참고용으로만 사용하세요.",
        icon="ℹ️",
    )

st.session_state.setdefault("category_input", "")
st.session_state.setdefault("curated_pick_label", "")

PLACEHOLDER = "— 선택하면 입력창에 채워집니다 —"
ANALYZED_TAG = "✅분석완료"


def _disp_label(cat, history: set[str]) -> str:
    tag = f"  ·  {ANALYZED_TAG}" if cat.name in history else ""
    return f"{cat.label()}{tag}"


# --- Curated category picker (outside the form so its buttons act immediately) ---
st.markdown("**드랍쇼핑 카테고리** — 마진·수요·경쟁 기준 선별 + AI 트렌딩 추천 (★ 많을수록 유리)")

_hist = categories.load_history()

if st.button("🔄 새 카테고리 20개 생성 (AI 트렌딩)", use_container_width=True):
    if not llm.any_available():
        st.warning("LLM API 키가 필요합니다 (GOOGLE_API_KEY 또는 ANTHROPIC_API_KEY). .env 설정 후 재시작", icon="⚠️")
    else:
        with st.spinner("AI(Gemini Flash 우선)로 트렌딩 카테고리 생성 중..."):
            gen = categories.generate_new_categories(20)
        if gen:
            st.toast(f"🔄 카테고리 목록 갱신 — 총 AI 추천 {len(gen)}개")
        else:
            st.warning("새 카테고리를 받지 못했습니다. 잠시 후 다시 시도하세요.", icon="⚠️")

_cats = list(categories.all_categories())
_label_to_name = {_disp_label(c, _hist): c.name for c in _cats}
_options = [PLACEHOLDER] + list(_label_to_name)
# Drop a stale selection that disappeared after the list was regenerated.
if st.session_state["curated_pick_label"] not in _options:
    st.session_state["curated_pick_label"] = PLACEHOLDER


def _sync_from_dropdown() -> None:
    name = _label_to_name.get(st.session_state["curated_pick_label"])
    if name:
        st.session_state["category_input"] = name


rand_col, pick_col = st.columns([1, 3])

# Render the random button BEFORE the selectbox so we may update the dropdown's
# state (Streamlit forbids mutating a widget's state after it is instantiated).
if rand_col.button("🎲 랜덤 추천", use_container_width=True):
    rc = categories.random_category()
    st.session_state["category_input"] = rc.name
    st.session_state["curated_pick_label"] = _disp_label(rc, _hist)
    st.toast(f"🎲 추천: {rc.name}")

pick_col.selectbox(
    "카테고리 목록",
    options=_options,
    key="curated_pick_label",
    label_visibility="collapsed",
    help=f"★ = 마진 / 수요 / 경쟁여유 (3점 만점). '{ANALYZED_TAG}' = 이미 분석한 카테고리. "
         "선택하면 아래 입력창에 자동 입력됩니다.",
    on_change=_sync_from_dropdown,
)

# Show the rationale of whichever known category is currently in the input box.
_current = categories.by_name(st.session_state["category_input"])
if _current is not None:
    tag = f"  ·  {ANALYZED_TAG}" if _current.name in _hist else ""
    st.caption(f"💡 **{_current.name}**{tag} — {_current.stars()}  \n{_current.reason}")

with st.expander(f"📋 카테고리 {len(_cats)}개 — 선정 기준 / 분석 이력"):
    st.dataframe(
        [{"카테고리": c.name, "마진": "★" * c.margin, "수요": "★" * c.demand,
          "경쟁여유": "★" * c.competition,
          "분석": ANALYZED_TAG if c.name in _hist else "—", "선정 이유": c.reason}
         for c in _cats],
        use_container_width=True, hide_index=True,
    )
    if _hist:
        st.caption(f"분석 완료 {len(_hist)}개: " + ", ".join(sorted(_hist)))

if st.button(f"🚀 전체 {len(_cats)}개 자동 분석", type="primary", use_container_width=True):
    bar = st.progress(0.0, text="준비 중...")
    batch = run_all_curated(
        progress=lambda done, total, name: bar.progress(done / total, text=f"{done}/{total}  ·  {name}")
    )
    bar.empty()
    st.session_state["batch"] = batch
    st.session_state["category_input"] = batch[0][0]   # pre-fill the #1 pick

if st.session_state.get("batch"):
    ui.render_batch(st.session_state["batch"])

st.divider()

with st.form("discovery"):
    st.text_input("분석할 카테고리", key="category_input",
                  placeholder="직접 입력하거나 위에서 선택 / 랜덤 추천 (예: wireless earbuds)")
    col_a, col_b, col_c = st.columns([2, 2, 3])
    market = col_a.text_input("타겟 시장", value="US")
    currency = col_b.text_input("통화", value="USD")
    force = col_c.checkbox("이미 분석한 카테고리도 다시 분석", value=False)
    submitted = st.form_submit_button("🔍 분석 실행", use_container_width=True)

if submitted:
    category = st.session_state["category_input"].strip()
    if not category:
        st.warning("카테고리를 입력하세요.")
        st.stop()
    if category in categories.load_history() and not force:
        st.warning(f'"{category}" 는 이미 분석했습니다. 다시 분석하려면 위의 체크박스를 켜세요.', icon="⚠️")
        st.stop()
    with st.spinner(f'"{category}" 분석 중...'):
        st.session_state["result"] = run_pipeline(
            category, target_market=market.strip() or "US", currency=currency.strip() or "USD"
        )
    categories.mark_analyzed(category)

result: PipelineResult | None = st.session_state.get("result")
if result is not None:
    v = result.verdict
    color = ui.DECISION_COLOR.get(v.decision, "#555")
    emoji = ui.DECISION_EMOJI.get(v.decision, "")

    st.divider()
    g_col, d_col = st.columns([1, 1.3])
    with g_col:
        st.markdown(ui.gauge_svg(v.total_score, v.decision), unsafe_allow_html=True)
    with d_col:
        st.markdown(
            f"<div style='font-size:40px;font-weight:800;color:{color}'>{emoji} {v.decision}</div>"
            f"<div style='color:#666'>총점 {v.total_score:.1f} / 100 "
            f"&nbsp;|&nbsp; 임계값: ≥70 GO · 50–69 WATCH · &lt;50 NO-GO</div>",
            unsafe_allow_html=True,
        )
    st.write(v.summary)

    # AI-written nuanced summary (quality tier — Claude Sonnet first). Cached
    # per category+decision so it is not regenerated on every rerun.
    if llm.any_available():
        key = (v.category, v.decision, round(v.total_score, 1))
        if st.session_state.get("ai_summary_key") != key:
            with st.spinner("AI 판정 요약 작성 중..."):
                st.session_state["ai_summary"] = verdict_ai.ai_verdict_summary(v)
            st.session_state["ai_summary_key"] = key
        if st.session_state.get("ai_summary"):
            st.info(st.session_state["ai_summary"], icon="🤖")

    st.subheader("스코어카드 (100점)")
    for line in v.breakdown:
        ui.factor_bar(ui.ko(line.name), line.score, line.max_score, line.detail)

    with st.expander("키워드"):
        st.dataframe(
            [{"키워드": k.term, "월 검색량(추정)": k.est_monthly_volume or "n/a",
              "근거": k.rationale} for k in result.keywords],
            use_container_width=True, hide_index=True,
        )

    with st.expander("모듈별 상세 지표"):
        t, b, rv, it, mg = result.trend, result.bsr, result.review, result.intent, result.margin
        st.markdown(f"**트렌드** — {t.notes}")
        st.markdown(f"**아마존 BSR** — {b.notes}")
        st.markdown(f"**리뷰** — {rv.notes}  \n불만 테마: {', '.join(rv.top_complaints) or '없음'}")
        st.markdown(f"**구매 의도** — {it.notes}  \n예시 쿼리: {', '.join(it.sample_queries) or '없음'}")
        st.markdown(f"**마진** — {mg.notes}")

    ui.scorecard_preview(result)

    fname, data = ui.excel_bytes(result)
    st.download_button(
        "⬇️ Excel 리포트 다운로드", data=data, file_name=fname,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    st.caption(f"리포트는 `output/{fname}` 에도 저장되었습니다.")

    st.divider()
    ui.render_strategy(result)

    st.divider()
    if v.decision == "GO":
        ui.render_go_tools(result)
    else:
        st.caption("ℹ️ 샵 이름·소싱 리스트 자동 생성은 GO 판정 카테고리에서 사용할 수 있습니다.")
