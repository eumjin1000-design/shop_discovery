"""GUI: upload a Spark scraper CSV and merge it into the current sourcing
result (adds the "③ Spark 실수집" sheet to the downloadable Excel).

Kept in its own module so app_render.py stays small. Called from
app_render.render_go_tools after the sourcing-list block.
"""
from __future__ import annotations

import os
import tempfile

import streamlit as st

from modules import sourcing_report, spark_import


def render_spark_import_section(category: str) -> None:
    res = (st.session_state.get("sourcing_res")
           if st.session_state.get("sourcing_cat") == category else None)
    if res is None:
        return  # nothing to merge into until a sourcing list exists

    st.markdown("**🛰️ Spark 실수집 CSV 병합** — 스크래퍼 결과 CSV를 올리면 "
                "Shopify 가격(판매가·정가·마진)을 계산해 Excel ③ 시트로 추가")
    c_m, c_d = st.columns(2)
    margin = c_m.slider("마진율", 0.10, 2.0, 0.70, 0.05, key="spark_margin")
    discount = c_d.slider("할인율 (정가 산정용)", 0.0, 0.6, 0.25, 0.05, key="spark_discount")
    up = st.file_uploader(
        "Spark CSV 업로드", type=["csv"], key="spark_csv",
        help="헤더: 상품명·상품코드·가격·별점·리뷰수·판매순위·상태 (UTF-8 / CP949)",
    )
    if up is not None and st.button("📥 CSV 병합", key="spark_merge", use_container_width=True):
        tmp = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
                tf.write(up.getvalue())
                tmp = tf.name
            rows = spark_import.parse_spark_csv(tmp)
        finally:
            if tmp and os.path.exists(tmp):
                os.unlink(tmp)
        if not rows:
            st.warning("CSV에서 행을 읽지 못했습니다. 헤더/인코딩을 확인하세요.", icon="⚠️")
        else:
            merged = spark_import.merge_with_sourcing(
                res, rows, margin_rate=margin, discount_rate=discount,
            )
            path = sourcing_report.write_sourcing_report(
                merged, shop_name=st.session_state.get("shop_name_selected"),
            )
            st.session_state["sourcing_res"] = merged
            st.session_state["sourcing_path"] = path
            st.toast(f"📥 Spark {len(rows)}행 병합 — 누적 {len(merged.spark_rows)}행, Excel ③ 시트 갱신")
            st.rerun()

    if res.spark_rows:
        st.write(f"Spark 실수집 누적 **{len(res.spark_rows)}개** — 미리보기 (상위 20개)")
        st.dataframe(
            [{"상품명": r.get("product_name"), "ASIN": r.get("asin"),
              "Amazon$": r.get("price_usd"), "Shopify판매가": r.get("shopify_sell"),
              "Shopify정가": r.get("shopify_msrp"), "마진$": r.get("margin_usd"),
              "마진율": r.get("margin_rate"), "별점": r.get("rating"),
              "리뷰수": r.get("review_count"), "판매순위": r.get("sales_rank")}
             for r in res.spark_rows[:20]],
            use_container_width=True, hide_index=True,
        )
