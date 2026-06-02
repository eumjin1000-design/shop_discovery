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

    # Spark broad mode needs only the code-side HF_TO_BROWSE_NODE +
    # HF_BROAD_KEYWORDS constants — no SQLite. Direct ASIN mode requires the
    # 1GB SQLite index (built locally via scripts/build_dataset_index.py),
    # which is git-ignored and therefore absent on Streamlit Cloud.
    db_ready = dataset_lookup.db_available()
    cats_db = dataset_lookup.list_categories() if db_ready else []
    cats_spark = sorted(spark_urls.HF_TO_BROWSE_NODE.keys())
    if not db_ready:
        st.info("ℹ️ Streamlit Cloud는 SQLite 인덱스 없이 작동 — **Spark 카테고리 "
                "URL 모드만 사용 가능**합니다 (5만+ ASIN 목표에 정확). "
                "직접 ASIN 모드는 로컬에서 `python scripts/build_dataset_index.py "
                "--all` 실행 후 사용하세요.")

    options = ["🌐 Spark 전체 16 카테고리 (207 URL, 5만+ 목표)",
               "🎯 분석한 카테고리만 (집중)",
               "✏️ 커스텀 키워드 (직접 입력)"]
    if db_ready:
        options.append("📦 직접 ASIN URL (53K /dp/ + 검색 확장)")
    mode = st.radio("타겟 모드", options, index=0, key="bulk_mode",
                    help="🌐 전체 = 모든 카테고리. 🎯 분석한 카테고리만 = 위에서 "
                    "분석한 카테고리에 집중된 8~12 Spark URL. ✏️ 커스텀 = 직접 "
                    "키워드 입력. 📦 직접 ASIN = 로컬 SQLite 인덱스 필요.")
    is_broad = mode.startswith("🌐")
    is_target = mode.startswith("🎯")
    is_custom = mode.startswith("✏️")
    is_direct = mode.startswith("📦")
    cats = cats_spark if is_broad else (cats_db if is_direct else [])

    selected, query_text, n_var, n_per_cat = [], "", 8, 3500
    if is_broad or is_direct:
        selected = st.multiselect("카테고리 선택", cats, default=cats,
                                  key="bulk_cats")
        if is_direct:
            n_per_cat = st.slider("카테고리당 최대 ASIN 수", 100,
                                  bulk_sourcing.HARD_CAP, value=3500,
                                  step=100, key="bulk_n")
            st.caption(f"예상 최대 행: **{len(selected)} × {n_per_cat:,} = "
                       f"{len(selected) * n_per_cat:,}개**")
        else:
            url_count = sum(len(spark_urls.HF_BROAD_KEYWORDS.get(c, [c]))
                            for c in selected)
            st.caption(f"**{len(selected)} 카테고리 → {url_count} 브로드 검색 URL** "
                       "(Home & Kitchen ≈ 26, Gift Cards ≈ 1)")
            with st.expander("📊 카테고리별 URL 배분"):
                preview = sorted(
                    [{"카테고리": c, "URL 수":
                      len(spark_urls.HF_BROAD_KEYWORDS.get(c, [c]))}
                     for c in selected], key=lambda x: -x["URL 수"])
                st.dataframe(preview, width="stretch", hide_index=True)
    elif is_target:
        analyzed = st.session_state.get("category_input", "")
        result = st.session_state.get("result")
        if not analyzed:
            st.warning("⚠️ 먼저 위 분석 폼에서 카테고리 분석을 진행하세요.")
            return
        if not result or not getattr(result, "keywords", None):
            st.warning("⚠️ 분석 결과가 없습니다. 위에서 '🔍 분석 실행'을 먼저 완료하세요.")
            return
        # 샵 컨셉명을 raw 쿼리로 쓰지 않고, 분석된 키워드 풀에서 직접 추출.
        # (Standing Workday Ergonomics 같은 컨셉명은 spark_query_list 필터에
        # 거부됨 — 분석 키워드는 이미 검증된 실 검색어라 안전.)
        query_text = analyzed   # label/UI 표시용. 실제 쿼리는 result.keywords
        st.info(f"타겟: **{analyzed}** (분석된 {len(result.keywords)}개 키워드 풀 사용)")
        n_var = st.slider("사용할 분석 키워드 수 (검색량 상위)", 3, 50, 12,
                          key="bulk_nvar_t")
        include_broad_t = st.checkbox(
            "🌐 매핑 카테고리의 브로드 키워드도 포함 (URL 수 ↑, 5만+ 목표 시 권장)",
            value=True, key="bulk_broad_t",
            help="예: reading nook → Home_and_Kitchen 브로드 키워드 26개 추가 "
                 "= 12+26=38 URL, 예상 ~34K 상품.")
        st.session_state["_bulk_target_broad"] = include_broad_t
        msg = f"→ {n_var}개 변형"
        if include_broad_t:
            msg += " + 매핑 카테고리 브로드 키워드 (예상 +26개)"
        st.caption(msg)
    elif is_custom:
        query_text = st.text_input("키워드 입력",
                                    placeholder="예: reading nook",
                                    key="bulk_custom_q")
        n_var = st.slider("키워드 변형 수", 3, 12, 8, key="bulk_nvar_c")
        include_broad_c = st.checkbox(
            "🌐 매핑 카테고리의 브로드 키워드도 포함",
            value=False, key="bulk_broad_c")
        st.session_state["_bulk_custom_broad"] = include_broad_c

    can_run = (selected if (is_broad or is_direct) else query_text)
    if not can_run:
        st.info("입력을 채우세요.")
        return

    if st.button("🎯 대량 소싱 리스트 생성", type="primary",
                 width="stretch", key="gen_bulk"):
        with st.spinner("처리 중..."):
            if is_broad:
                res = bulk_sourcing.spark_category_list(selected)
            elif is_direct:
                res = bulk_sourcing.bulk_sourcing_list(selected,
                                                       n_per_cat=n_per_cat)
            elif is_target:
                # 분석된 키워드 풀에서 검색량 상위 N개 → Spark URL (샵 컨셉명
                # 거부 우회: 분석 키워드는 이미 실 검색어로 검증됨)
                broad = st.session_state.get("_bulk_target_broad", False)
                top_kws = sorted(result.keywords,
                                 key=lambda k: getattr(k, "est_monthly_volume", 0) or 0,
                                 reverse=True)[:n_var]
                res = bulk_sourcing.spark_keywords_list(
                    keywords=[k.term for k in top_kws],
                    category_label=analyzed, include_broad=broad)
            else:  # is_custom
                broad = st.session_state.get("_bulk_custom_broad", False)
                res = bulk_sourcing.spark_query_list(
                    query_text, n_variations=n_var, include_broad=broad)
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
