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
from main import run_categories, run_pipeline
from modules import categories, llm, verdict_ai
from modules.models import PipelineResult

ESTIMATED_SECS_PER_CAT = 4.0  # rough upfront hint; live ETA refines it after #1


def _run_batch(names: list[str], label: str) -> None:
    """Run a slice of categories, merge into the saved ranking, and persist it."""
    if not names:
        return
    st.caption(
        f"⏳ {label} {len(names)}개 분석 — 예상 ~{int(len(names) * ESTIMATED_SECS_PER_CAT)}초 "
        "(실제 API 사용 시 더 걸릴 수 있음)"
    )
    bar = st.progress(0.0, text=f"0/{len(names)} 분석 준비 중...")

    def _cb(done: int, total: int, name: str, eta: float) -> None:
        bar.progress(done / total, text=f"{done}/{total} 분석 중... ({name}) — 남은 시간 ~{eta:.0f}초")

    results = run_categories(names, progress=_cb)
    bar.empty()
    merged: dict[str, dict] = {r["name"]: r for r in st.session_state.get("batch_rows", [])}
    for r in ui.pipeline_rows(results):
        merged[r["name"]] = r
    rows = sorted(merged.values(), key=lambda r: r["total"], reverse=True)
    st.session_state["batch_rows"] = rows
    categories.save_batch_results(rows)            # 중간 저장 — survives restart
    st.session_state["category_input"] = rows[0]["name"]
    st.toast(f"✅ {label} 분석 완료 — 누적 {len(rows)}개, 1위 {rows[0]['name']}")
    st.rerun()

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

# Restore the last batch ranking from disk (survives an app restart).
if "batch_rows" not in st.session_state:
    _saved = categories.load_batch_results()
    if _saved:
        st.session_state["batch_rows"] = _saved

# Decision map: analysis history (name -> GO/WATCH/NO-GO) + live result + batch.
_dec_map: dict[str, str | None] = dict(categories.load_history_map())
_live = st.session_state.get("result")
if _live is not None:
    _dec_map[_live.verdict.category] = _live.verdict.decision
for _r in st.session_state.get("batch_rows", []):
    _dec_map.setdefault(_r["name"], _r.get("decision"))
_cats = list(categories.all_categories())
_selected = st.session_state["category_input"].strip()

st.subheader("🧭 카테고리 선택")
catalog.render_stats(_cats, _dec_map, len(categories.load_history()))
catalog.render_manage_buttons()
catalog.render_category_grid(_cats, _dec_map, _selected)

# Rationale of the currently selected curated category, if any.
_current = categories.by_name(_selected)
if _current is not None:
    tag = "  ·  ✅ 분석완료" if _current.name in categories.load_history() else ""
    st.caption(f"💡 **{_current.name}**{tag} — {_current.stars()}  \n{_current.reason}")

with st.expander(f"📋 카테고리 {len(_cats)}개 — 선정 기준 / 분석 이력 (표 보기)"):
    st.dataframe(
        [{"카테고리": c.name, "마진": "★" * c.margin, "수요": "★" * c.demand,
          "경쟁여유": "★" * c.competition,
          "분석": _dec_map.get(c.name) or "—", "선정 이유": c.reason}
         for c in _cats],
        use_container_width=True, hide_index=True,
    )

_n = len(_cats)
_chunks = [(i, min(i + 10, _n)) for i in range(0, _n, 10)]   # [(0,10),(10,20),...]
st.markdown("**자동 분석** — 10개 단위 부분 배치 또는 전체. 완료 즉시 아래 순위 테이블이 갱신됩니다.")
_btn_cols = st.columns(len(_chunks) + 1)
for _ci, (_a, _b) in enumerate(_chunks):
    if _btn_cols[_ci].button(f"{_a + 1}~{_b}번 분석", use_container_width=True, key=f"batch_{_a}"):
        _run_batch([c.name for c in _cats[_a:_b]], f"{_a + 1}~{_b}번")
if _btn_cols[-1].button(f"🚀 전체 분석 ({_n}개)", type="primary", use_container_width=True, key="batch_all"):
    _run_batch([c.name for c in _cats], "전체")

if st.session_state.get("batch_rows"):
    ui.render_batch(st.session_state["batch_rows"])

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
    categories.mark_analyzed(category, decision=st.session_state["result"].verdict.decision)
    st.rerun()

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
