"""Streamlit UI for the bulk sourcing mode.

Renders a single self-contained section after the verdict/sourcing area:
``🎯 대량 소싱 모드 (LLM 우회·100% 실 ASIN)``. Lets the user select any
combination of the indexed HF categories, choose how many ASINs per
category, preview total row count live, and emit Excel + Spark .txt
directly from the SQLite index — no LLM, no analysis prerequisite.

The output reuses :func:`modules.sourcing_report.write_sourcing_report` so
files land in ``output/`` with the same Spark-compatible format as the
LLM-driven flow.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from modules import bulk_sourcing, dataset_lookup, sourcing_report, spark_urls


def render_bulk_sourcing_section() -> None:
    """Top-level entry point — call once at the bottom of ``app.py``."""
    st.divider()
    st.header("🎯 대량 소싱 모드")
    st.caption(
        "LLM 우회 · 100% 실 `/dp/{ASIN}` URL · 5만+ ASIN을 1분 안에. "
        "분석/판정 없이 데이터셋(HF Amazon-Reviews-2023)에서 카테고리별 상위 "
        "리뷰 ASIN을 직접 추출합니다. Spark 일괄 입력용 .txt 동시 생성."
    )

    if not dataset_lookup.db_available():
        st.warning("⚠️ 로컬 데이터셋 인덱스가 없습니다. "
                   "`python scripts/build_dataset_index.py --all` 실행 후 사용하세요.")
        return

    cats = dataset_lookup.list_categories()
    if not cats:
        st.warning("⚠️ 인덱스에 카테고리가 없습니다.")
        return

    mode = st.radio(
        "출력 모드",
        ["🎯 Spark 카테고리 URL (브로드, 추천)",
         "📦 직접 ASIN URL (53K /dp/ + 검색 확장)"],
        index=0, key="bulk_mode", horizontal=True,
        help="Spark 카테고리 URL = PDF 가이드(11/24) 형식. URL당 수백~수천 "
             "상품 수확 (6h ≈ 900). 직접 ASIN URL = 매행이 특정 베스트셀러, "
             "Spark 수확량 적음.",
    )
    is_spark = mode.startswith("🎯")

    selected = st.multiselect(
        "카테고리 선택 (Ctrl/Shift 다중 선택)", cats,
        default=cats, key="bulk_cats",
        help="기본은 전체 16개 카테고리. 일부만 선택 가능.",
    )
    if not is_spark:
        n_per_cat = st.slider(
            "카테고리당 최대 ASIN 수", 100, bulk_sourcing.HARD_CAP,
            value=3500, step=100, key="bulk_n",
            help=f"카테고리당 최대 {bulk_sourcing.HARD_CAP:,}.",
        )
        st.caption(f"예상 최대 행 수: **{len(selected)} × {n_per_cat:,} = "
                   f"{len(selected) * n_per_cat:,}개**")
    else:
        url_count = sum(len(spark_urls.HF_BROAD_KEYWORDS.get(c, [c])) for c in selected)
        st.caption(
            f"**{len(selected)} 카테고리 → {url_count} 브로드 검색 URL** — "
            "Amazon 카테고리 깊이에 비례하여 자동 배분 (Home & Kitchen ≈ 26개, "
            "Gift Cards ≈ 1개). Spark가 URL당 ~6시간 페이지네이션하며 "
            "수백~수천 상품을 수확합니다."
        )
        with st.expander("📊 카테고리별 URL 배분 미리보기"):
            preview = [
                {"카테고리": c,
                 "URL 수": len(spark_urls.HF_BROAD_KEYWORDS.get(c, [c]))}
                for c in selected
            ]
            preview.sort(key=lambda x: -x["URL 수"])
            st.dataframe(preview, width="stretch", hide_index=True)

    if not selected:
        st.info("카테고리를 1개 이상 선택하세요.")
        return

    if st.button("🎯 대량 소싱 리스트 생성", type="primary",
                 width="stretch", key="gen_bulk"):
        with st.spinner(f"{len(selected)} 카테고리 처리 중..."):
            if is_spark:
                res = bulk_sourcing.spark_category_list(selected)
            else:
                res = bulk_sourcing.bulk_sourcing_list(
                    selected, n_per_cat=n_per_cat)
            path = sourcing_report.write_sourcing_report(
                res, shop_name=st.session_state.get("shop_name_selected"))
        st.session_state["bulk_res"] = res
        st.session_state["bulk_path"] = path

    res = st.session_state.get("bulk_res")
    if not res:
        return

    is_spark_res = bool(res.rows) and not res.rows[0].asin
    if is_spark_res:
        st.success(f"✅ {res.total} Spark 브로드 검색 URL 생성 완료")
        st.write(res.summary)
        st.caption("Spark `.txt`에는 각 URL이 한 줄씩 들어가며, Spark가 URL당 "
                   "6시간 가량 페이지네이션으로 ~수백~수천 상품 수확합니다.")
        st.dataframe(
            [{"#": i + 1, "카테고리": r.subcategory, "키워드": r.keyword,
              "노드 ID": r.amazon_node_id, "Spark URL": r.search_url}
             for i, r in enumerate(res.rows)],
            width="stretch", hide_index=True,
        )
    else:
        st.success(f"✅ {res.total:,}개 유니크 ASIN 추출 완료 (모두 실 `/dp/` URL)")
        st.write(res.summary)
        st.caption("Excel은 `/dp/` URL + 검색 확장 URL 두 컬럼 모두 포함.")
        st.dataframe(
            [{"#": i + 1, "카테고리": r.subcategory, "ASIN": r.asin,
              "상품명": r.base_product, "브랜드": r.brand or "—",
              "리뷰수": r.review_count, "예상가격($)": r.est_price,
              "/dp/ URL": r.amazon_url, "검색 확장 URL": r.search_url}
             for i, r in enumerate(res.rows[:30])],
            width="stretch", hide_index=True,
        )

    path = st.session_state.get("bulk_path")
    if path:
        excel_path = Path(path)
        txt_path = excel_path.with_suffix(".txt")
        col_a, col_b = st.columns(2)
        with col_a:
            with open(excel_path, "rb") as fh:
                st.download_button(
                    f"⬇️ Excel ({res.total:,} 행)", data=fh.read(),
                    file_name=excel_path.name, width="stretch",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
        with col_b:
            if txt_path.exists():
                with open(txt_path, "rb") as fh:
                    st.download_button(
                        "⬇️ Spark 일괄입력 .txt", data=fh.read(),
                        file_name=txt_path.name, width="stretch",
                        mime="text/plain",
                    )
