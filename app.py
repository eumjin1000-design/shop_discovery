"""Streamlit GUI for Shop Discovery.

Run with:
    streamlit run app.py

Layout: header (🐙 logo + LLM badge) · stat cards · category list (label +
manage buttons + amber warning + 3-col card grid) · button row (랜덤 추천 ·
전체 자동 분석) · single-category analysis (verdict panel + scorecard + 전략
기준 + Excel/소싱). Rendering lives in app_render.py / app_catalog_ui.py; the
pipeline lives in main.run_pipeline.
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
st.set_page_config(page_title="샵 디스커버리", page_icon="🐙", layout="centered")
ui.render_header(llm.provider_label(), llm.any_available())

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
_n = len(_cats)
_selected = st.session_state["category_input"].strip()

# 1) Stat cards
catalog.render_stats(_cats, _dec_map, len(categories.load_history()))
st.divider()

# 2) Category list area: label + manage buttons + amber warning + card grid
catalog.render_list_header()
catalog.render_category_grid(_cats, _dec_map, _selected, cols=3)

_current = categories.by_name(_selected)
if _current is not None:
    tag = "  ·  ✅ 분석완료" if _current.name in categories.load_history() else ""
    st.caption(f"💡 **{_current.name}**{tag} — {_current.stars()}  \n{_current.reason}")

with st.expander(f"📋 카테고리 {_n}개 — 선정 기준 / 분석 이력 (표 보기)"):
    st.dataframe(
        [{"카테고리": c.name, "마진": "★" * c.margin, "수요": "★" * c.demand,
          "경쟁여유": "★" * c.competition,
          "분석": _dec_map.get(c.name) or "—", "선정 이유": c.reason}
         for c in _cats],
        use_container_width=True, hide_index=True,
    )

# 3) Button row: 🎲 랜덤 추천 (outline, left)  ·  ▷ 전체 N개 자동 분석 (red, right)
_b_left, _b_right = st.columns([1, 1])
if _b_left.button("🎲 랜덤 추천", use_container_width=True, type="secondary", key="rand_pick"):
    _rc = categories.random_category()
    st.session_state["category_input"] = _rc.name
    st.toast(f"🎲 추천: {_rc.name}")
    st.rerun()
if _b_right.button(f"▷ 전체 {_n}개 자동 분석", use_container_width=True, type="primary", key="batch_all"):
    _run_batch([c.name for c in _cats], "전체")

with st.expander("⏳ 10개 단위로 나눠 분석 (부분 배치)"):
    _chunks = [(i, min(i + 10, _n)) for i in range(0, _n, 10)]
    _ccols = st.columns(max(1, len(_chunks)))
    for _ci, (_a, _b) in enumerate(_chunks):
        if _ccols[_ci].button(f"{_a + 1}~{_b}번", use_container_width=True, key=f"batch_{_a}"):
            _run_batch([c.name for c in _cats[_a:_b]], f"{_a + 1}~{_b}번")

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

    st.subheader(f"📊 분석 결과 — {v.category}")
    ui.render_verdict_panel(v)
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
