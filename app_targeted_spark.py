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

    st.markdown("**🎯 이 카테고리 Spark URL** — 분석한 카테고리에 집중된 8~12 URL")
    st.caption(f"`{category}` · {mapping_note} · 각 URL이 Spark에서 페이지네이션")

    n_var = st.slider("키워드 변형 수", 3, 12, 8, key="tgt_spark_n",
                      help="기본 8개. 변형 예: 원본, ideas, set, kit, "
                           "accessories, for kids, decor, essentials, best ...")

    if st.button("🎯 이 카테고리 Spark URL 생성", key="gen_targeted",
                 width="stretch"):
        with st.spinner("Spark URL 생성 중..."):
            res = bulk_sourcing.spark_query_list(category, n_variations=n_var)
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
