"""GO-category tools: 샵 이름 생성 + 소싱 리스트 생성.

Extracted from :mod:`app_render` to keep that file under the 300-line
hard limit. The single public entry point is :func:`render_go_tools` which
:mod:`app_render.render_go_tools` delegates to.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from modules import shop_namer, sourcing, sourcing_report


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


def _sourcing_controls() -> tuple[int, int, int, int, bool]:
    """Render the sourcing-list controls and return (n_subs, n_vars, n_pages,
    n_passes, verify_urls). 🚀 정확도 최대 preset overwrites session_state
    values before the widgets render so the user sees the new values."""
    if st.button("🚀 정확도 최대 (서브 15·변형 10·페이지 5·1패스)",
                 key="src_preset", help="안전선 내 최대값으로 자동 세팅"):
        st.session_state["src_subs"] = 15
        st.session_state["src_vars"] = 10
        st.session_state["src_pages"] = 5
        st.session_state["src_passes"] = 1
        st.rerun()
    c_sub, c_var = st.columns(2)
    n_subs = c_sub.number_input("서브카테고리 수", min_value=1, max_value=30,
        value=st.session_state.get("src_subs", sourcing.DEFAULT_SUBS),
        step=1, key="src_subs",
        help="LLM이 생성할 서브카테고리 개수. 권장 6-15. 너무 크면 LLM 응답 잘림")
    n_vars = c_var.number_input("변형 수", min_value=1, max_value=20,
        value=st.session_state.get("src_vars", sourcing.DEFAULT_VARIANTS),
        step=1, key="src_vars",
        help="상품당 변형 라벨 수 (Standard/Compact/...). 권장 5-10")
    c_pg, c_ps = st.columns(2)
    n_pages = c_pg.slider("페이지 깊이", 1, 5,
        st.session_state.get("src_pages", sourcing.DEFAULT_PAGES),
        key="src_pages",
        help="각 검색 URL을 page 1..N으로 사전 확장. 5까지가 정확도 안전선")
    n_passes = c_ps.slider("LLM 패스 수", 1, 3,
        st.session_state.get("src_passes", sourcing.DEFAULT_PASSES),
        key="src_passes",
        help="2 이상이면 LLM을 N번 호출해 서로 다른 서브카테고리 머지. 시간 N배")
    total = int(n_subs) * sourcing.PRODUCTS_N * int(n_vars) * int(n_pages) * int(n_passes)
    st.caption(
        f"= {n_subs}({n_passes}패스) × {sourcing.PRODUCTS_N} × {n_vars} × {n_pages} "
        f"= **최대 {total:,}개** URL (LLM 중복 제거 후 그 이하)"
    )
    verify_urls = st.checkbox("🔍 URL 검증 (죽은 ASIN 제거, +30~45초)",
        value=False, key="src_verify",
        help="HF dataset(2023-09) ASIN을 GET-stream으로 검증해 404/CAPTCHA 제거.")
    return int(n_subs), int(n_vars), int(n_pages), int(n_passes), verify_urls


def _sourcing_preview_and_dl(res: sourcing.SourcingResult, path: str) -> None:
    seen, prev = set(), []
    for r in res.rows:
        k = (r.subcategory, r.base_product)
        if k in seen:
            continue
        seen.add(k)
        prev.append({"#": len(prev) + 1, "서브카테고리": r.subcategory,
                     "브랜드(추정)": r.brand or "—", "상품명": r.base_product,
                     "Amazon URL": r.amazon_url, "예상가격($)": r.est_price,
                     "키워드": r.keyword, "ASIN": r.asin or "—",
                     "리뷰수": r.review_count or "—"})
        if len(prev) >= 30:
            break
    st.write(f"{res.summary}  ·  미리보기 (유니크 상품 {len(prev)}개)")
    st.dataframe(prev, width="stretch", hide_index=True)
    with st.expander("📋 키워드만 복사 (우측 상단 아이콘)"):
        st.code("\n".join(dict.fromkeys(r.keyword for r in res.rows if r.keyword)),
                language=None)
    txt_path = Path(path).with_suffix(".txt")
    d_xlsx, d_txt = st.columns(2)
    d_xlsx.download_button("⬇️ Excel 다운로드", data=Path(path).read_bytes(),
        file_name=Path(path).name, key="sourcing_dl", width="stretch",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if txt_path.exists():
        d_txt.download_button("⬇️ Spark 일괄입력 .txt",
            data=txt_path.read_bytes(), file_name=txt_path.name,
            key="sourcing_txt_dl", width="stretch", mime="text/plain")
    st.caption(
        f"`output/{Path(path).name}` (Amazon URL = 셀 하이퍼링크) + `{txt_path.name}` "
        "(`카테고리|서브카테고리|URL` — Spark 일괄입력 탭에 붙여넣고 작업 시작)"
    )


def _sourcing_block(category: str) -> None:
    st.markdown("**📦 소싱 리스트 자동 생성** — 서브카테고리 × 상품 × 변형 × 페이지 (Amazon 노드·Prime·리뷰순 URL, Spark 수집용)")
    n_subs, n_vars, n_pages, n_passes, verify_urls = _sourcing_controls()
    if st.button("📦 소싱 리스트 생성", key="gen_sourcing"):
        spinner_text = ("생성 + URL 검증 중..." if verify_urls else
                        f"소싱 리스트 생성 중... ({n_passes}패스, ~{n_passes * 15}초)")
        with st.spinner(spinner_text):
            res = sourcing.generate_sourcing_list(
                category, n_subs=n_subs, n_variants=n_vars,
                passes=n_passes, pages=n_pages, verify_urls=verify_urls,
            )
            path = sourcing_report.write_sourcing_report(
                res, shop_name=st.session_state.get("shop_name_selected"),
            )
        st.session_state["sourcing_res"] = res
        st.session_state["sourcing_path"] = path
        st.session_state["sourcing_cat"] = category
    res = (st.session_state.get("sourcing_res")
           if st.session_state.get("sourcing_cat") == category else None)
    if res:
        _sourcing_preview_and_dl(res, st.session_state["sourcing_path"])


def render_go_tools_blocks(category: str) -> None:
    """샵 이름 + 소싱 리스트 블록 — Spark import 섹션은 호출자가 별도 렌더."""
    _shop_name_block(category)
    st.divider()
    _sourcing_block(category)
