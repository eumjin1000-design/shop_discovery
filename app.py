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

import app_backup_ui
import app_catalog_ui as catalog
import app_keepa_ui
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

# Custom red cursor (browser-only, 2x size). SVG data URI — works in all
# modern browsers; OS-level cursor is unchanged.
_ARROW = ("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' "
          "width='64' height='64' viewBox='0 0 32 32'>"
          "<path d='M3 2 L3 25 L9 19 L13 28 L17 27 L13 18 L21 18 Z' "
          "fill='%23E50914' stroke='white' stroke-width='1.2'/></svg>")
_HAND = ("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' "
         "width='64' height='64' viewBox='0 0 32 32'>"
         "<circle cx='16' cy='16' r='9' fill='%23E50914' stroke='white' "
         "stroke-width='1.5'/><circle cx='16' cy='16' r='3' fill='white'/>"
         "</svg>")
# Scoped to body + interactive elements only (avoid '*' which caused React
# DOM reconciliation errors on Streamlit Cloud — see NotFoundError on
# removeChild). Streamlit Cloud users should hard-reload (Ctrl+Shift+R)
# after any deploy if they hit DOM errors.
st.markdown(
    f"<style>body{{cursor:url(\"{_ARROW}\") 0 0,default}} "
    f"button,a{{cursor:url(\"{_HAND}\") 16 16,pointer}}</style>",
    unsafe_allow_html=True,
)

ui.render_header(llm.provider_label(), llm.any_available())
app_keepa_ui.render_sidebar()

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
        [{"카테고리": c.name,
          "가치": "★" * getattr(c, "perceived_value", 0),
          "해결": "★" * getattr(c, "problem_solving", 0),
          "틈새": "★" * getattr(c, "niche_specificity", 0),
          "분석": _dec_map.get(c.name) or "—", "선정 이유": c.reason}
         for c in _cats],
        width="stretch", hide_index=True,
    )

# Pre-execution Keepa token warning for the full-batch action.
from modules import keepa_status as _ks
_batch_cost = _ks.estimate_analysis_cost(_n)
app_keepa_ui.preflight_banner(_batch_cost, f"전체 {_n}개 자동 분석")
st.caption("💡 24시간 이내 분석한 카테고리는 캐시가 적용되어 토큰이 소모되지 않습니다.")

# Mock-fallback safety: when Keepa is configured but tokens are short, relabel
# the red full-batch button so the user knowingly opts into mock data.
_batch_mock = app_keepa_ui.mock_fallback_expected(_batch_cost)
_batch_label = (f"⚠️ 전체 {_n}개 분석 (Mock 포함 강제 진행)" if _batch_mock
                else f"▷ 전체 {_n}개 자동 분석")

# 3) Button row: 🎲 랜덤 추천 (outline, left)  ·  ▷ 전체 N개 자동 분석 (red, right)
_b_left, _b_right = st.columns([1, 1])
if _b_left.button("🎲 랜덤 추천", width="stretch", type="secondary", key="rand_pick"):
    _rc = categories.random_category()
    st.session_state["category_input"] = _rc.name
    st.toast(f"🎲 추천: {_rc.name}")
    st.rerun()
if _b_right.button(_batch_label, width="stretch", type="primary", key="batch_all"):
    _run_batch([c.name for c in _cats], "전체")

with st.expander("⏳ 10개 단위로 나눠 분석 (부분 배치)"):
    _chunks = [(i, min(i + 10, _n)) for i in range(0, _n, 10)]
    _ccols = st.columns(max(1, len(_chunks)))
    for _ci, (_a, _b) in enumerate(_chunks):
        if _ccols[_ci].button(f"{_a + 1}~{_b}번", width="stretch", key=f"batch_{_a}"):
            _run_batch([c.name for c in _cats[_a:_b]], f"{_a + 1}~{_b}번")

if st.session_state.get("batch_rows"):
    ui.render_batch(st.session_state["batch_rows"])

st.divider()

app_backup_ui.render_backup_section()
app_keepa_ui.preflight_banner(_ks.COST_PER_CATEGORY, "단일 분석")
st.caption("💡 24시간 이내 분석한 카테고리는 캐시가 적용되어 토큰이 소모되지 않습니다.")
with st.form("discovery"):
    st.text_input("분석할 카테고리", key="category_input",
                  placeholder="직접 입력하거나 위에서 선택 / 랜덤 추천 (예: wireless earbuds)")
    col_a, col_b, col_c = st.columns([2, 2, 3])
    market = col_a.text_input("타겟 시장", value="US")
    currency = col_b.text_input("통화", value="USD")
    force = col_c.checkbox("이미 분석한 카테고리도 다시 분석", value=False)
    submitted = st.form_submit_button("🔍 분석 실행", width="stretch")

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

    # Buyer demographic (LLM-estimated, from intent_check pass)
    it = result.intent
    if it.primary_age or it.secondary_age:
        ages = [a for a in (it.primary_age, it.secondary_age) if a]
        st.markdown(f"**🎯 주 구매 연령대** · {' / '.join(ages)}"
                    f"{' — ' + it.age_rationale if it.age_rationale else ''}")

    st.subheader("스코어카드 (100점)")
    for line in v.breakdown:
        ui.factor_bar(ui.ko(line.name), line.score, line.max_score, line.detail)

    with st.expander("키워드"):
        st.dataframe(
            [{"키워드": k.term, "월 검색량(추정)": k.est_monthly_volume or "n/a",
              "근거": k.rationale} for k in result.keywords],
            width="stretch", hide_index=True,
        )
        st.caption("⬇️ 키워드만 한 번에 복사 (우측 상단 📋 아이콘 클릭)")
        st.code("\n".join(k.term for k in result.keywords), language=None)

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
        width="stretch",
    )
    st.caption(f"리포트는 `output/{fname}` 에도 저장되었습니다.")

    st.divider()
    ui.render_strategy(result)

    st.divider()
    if v.decision == "GO":
        ui.render_go_tools(result)
        from app_targeted_spark import render_targeted_spark_section  # noqa: E402
        st.divider()
        render_targeted_spark_section(result.request.category)
    else:
        st.caption("ℹ️ 샵 이름·소싱 리스트 자동 생성은 GO 판정 카테고리에서 사용할 수 있습니다.")

from app_bulk import render_bulk_sourcing_section  # noqa: E402
render_bulk_sourcing_section()
