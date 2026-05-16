"""GO-category Spark URL section — rendered right after the verdict panel.

Generates 5~12 Spark search URLs focused on the **currently analyzed**
category (e.g. ``"reading nook"``) using
:func:`modules.bulk_sourcing.spark_query_list`. Complements
:mod:`app_bulk`'s broad-mode 207-URL output by letting the user grab a
small, niche-specific Spark feed without leaving the verdict screen.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from modules import bulk_sourcing, dataset_lookup, sourcing_report, spark_urls


def render_targeted_spark_section(category: str) -> None:
    """Render the inline GO-category Spark URL block."""
    if not category:
        return
    hf_cat = dataset_lookup.map_category(category)
    node = spark_urls.HF_TO_BROWSE_NODE.get(hf_cat or "", "")
    mapping_note = (f"매핑: **{hf_cat}** (node `{node}`)"
                    if hf_cat else "매핑: 없음 — 일반 검색 URL")

    st.markdown("**🎯 이 카테고리 Spark URL** — 분석한 카테고리에 집중된 URL 묶음")
    st.caption(f"`{category}` · {mapping_note} · 각 URL은 시스템이 직접 페이지 사전 확장")

    if st.button("🚀 정확도 최대 (변형 20·페이지 5·브로드 ON)",
                 key="tgt_preset", help="안전선 내 최대값으로 자동 세팅"):
        st.session_state["tgt_spark_n"] = 20
        st.session_state["tgt_pages"] = 5
        st.session_state["tgt_broad"] = True
        st.rerun()
    c_var, c_pg = st.columns(2)
    n_var = c_var.number_input("키워드 변형 수", min_value=1, max_value=20,
        value=st.session_state.get("tgt_spark_n", 12),
        step=1, key="tgt_spark_n",
        help="원본 + SEO 친화 modifier (best/top rated/premium/...). 최대 20개")
    n_pages = c_pg.slider("페이지 깊이", 1, 5,
        st.session_state.get("tgt_pages", 1), key="tgt_pages",
        help="각 검색 URL을 page 1..N으로 사전 확장. 5까지가 정확도 안전선")
    include_broad = st.checkbox(
        f"🌐 매핑 카테고리({hf_cat or '미매핑'})의 브로드 키워드도 포함",
        value=st.session_state.get("tgt_broad", True), key="tgt_broad",
        help="활성 시 매핑 HF 카테고리의 10~26개 브로드 키워드도 추가")

    if st.button("🎯 이 카테고리 Spark URL 생성", key="gen_targeted",
                 width="stretch"):
        with st.spinner("Spark URL 생성 중..."):
            res = bulk_sourcing.spark_query_list(
                category, n_variations=int(n_var), include_broad=include_broad,
                pages=int(n_pages))
            path = sourcing_report.write_sourcing_report(
                res, shop_name=st.session_state.get("shop_name_selected"))
        st.session_state["targeted_res"] = res
        st.session_state["targeted_path"] = path

    res = st.session_state.get("targeted_res")
    path = st.session_state.get("targeted_path")
    if not res or not path:
        return
    # Only show this section's result if it matches the current category
    if not res.category.endswith(category):
        return

    st.success(f"✅ {res.total}개 Spark URL 생성 완료 ({category})")
    st.caption(res.summary)
    st.dataframe(
        [{"#": i + 1, "키워드": r.keyword, "노드": r.amazon_node_id or "—",
          "Spark URL": r.search_url}
         for i, r in enumerate(res.rows)],
        width="stretch", hide_index=True,
    )

    excel_path = Path(path)
    txt_path = excel_path.with_suffix(".txt")
    col_a, col_b = st.columns(2)
    with col_a:
        with open(excel_path, "rb") as fh:
            st.download_button(
                f"⬇️ Excel ({res.total} URL)", data=fh.read(),
                file_name=excel_path.name, width="stretch",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="targeted_xlsx",
            )
    with col_b:
        if txt_path.exists():
            with open(txt_path, "rb") as fh:
                st.download_button(
                    "⬇️ Spark 일괄입력 .txt", data=fh.read(),
                    file_name=txt_path.name, width="stretch",
                    mime="text/plain", key="targeted_txt",
                )
