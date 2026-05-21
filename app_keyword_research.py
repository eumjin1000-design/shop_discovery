"""Keyword Research view — calls the Node.js HTTP API (server/index.js).

Rendered as a Streamlit page (see pages/). The keyword pipeline lives in
Node.js (server/lib/*), exposed at POST /api/keywords/research. This view
is a thin client over that API.

⚠️ The Node API runs on localhost:8787 — reachable only when both this
Streamlit app AND `npm run serve` run on the same machine. On Streamlit
Cloud the call fails; we surface a clear "server not running" message
instead of crashing.
"""
from __future__ import annotations

import io
import os

import pandas as pd
import requests
import streamlit as st

API_BASE = os.environ.get("KEYWORD_API_BASE", "http://localhost:8787")
RESEARCH_URL = f"{API_BASE}/api/keywords/research"
CACHE_URL = f"{API_BASE}/api/keywords/cache/stats"
_TIMEOUT = 130  # slightly above the API's 120s cap


def _kd_badge(kd: float) -> str:
    if kd <= 30:
        return "💎"
    if kd <= 60:
        return "⭐"
    return "🔴"


def _rows_to_csv(rows: list[dict]) -> bytes:
    if not rows:
        return b""
    df = pd.DataFrame(rows)
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8-sig")  # BOM → Excel 한글 안전


def _call_research(payload: dict) -> dict | None:
    """POST to the Node API. Returns parsed JSON or None (with a UI message)."""
    try:
        resp = requests.post(RESEARCH_URL, json=payload, timeout=_TIMEOUT)
    except requests.ConnectionError:
        st.error(
            f"Node API 서버에 연결할 수 없습니다 ({API_BASE}).\n\n"
            "로컬에서 `npm run serve` 로 서버를 먼저 띄우세요. "
            "(Streamlit Cloud에서는 localhost API를 호출할 수 없습니다.)",
            icon="🔌",
        )
        return None
    except requests.Timeout:
        st.error("요청이 시간 초과되었습니다 (130초). 시드 수를 줄여 다시 시도하세요.", icon="⏱️")
        return None
    if resp.status_code != 200:
        try:
            body = resp.json()
            st.error(f"[{body.get('code', 'ERROR')}] {body.get('error', resp.text)}", icon="⚠️")
        except ValueError:
            st.error(f"HTTP {resp.status_code}: {resp.text[:200]}", icon="⚠️")
        return None
    return resp.json()


def _render_input() -> dict | None:
    """Render the input form. Returns the request payload on submit, else None."""
    st.markdown("**시드 키워드** — 한 줄에 하나, 최대 20개")
    seeds_raw = st.text_area(
        "시드 키워드", label_visibility="collapsed", height=120,
        placeholder="korean skincare\nsnail mucin\nglass skin",
        key="kw_seeds",
    )
    c1, c2 = st.columns([1, 2])
    country = c1.selectbox("국가", ["US", "KR", "JP", "GB"], index=0, key="kw_geo")
    keepa_on = c2.toggle("🪙 Amazon 검증 포함 (Keepa)", value=False, key="kw_keepa")
    top_n = 5
    if keepa_on:
        top_n = st.number_input(
            "Keepa 검증할 상위 보석 수 (top_n)", min_value=1, max_value=20,
            value=5, step=1, key="kw_topn",
            help="검색량 상위 N개 보석만 Keepa로 검증 (토큰 절약)",
        )
    if st.button("🔍 분석 시작", type="primary", width="stretch", key="kw_run"):
        seeds = [s.strip() for s in seeds_raw.splitlines() if s.strip()][:20]
        if not seeds:
            st.warning("시드 키워드를 한 개 이상 입력하세요.", icon="⚠️")
            return None
        return {
            "seeds": seeds, "market": country, "language": "en",
            "validate_with_keepa": bool(keepa_on), "top_n": int(top_n),
        }
    return None


def _render_results(data: dict, keepa_on: bool) -> None:
    meta = data.get("metadata", {})
    gems = data.get("gems", [])
    allkw = data.get("all", [])

    if not meta.get("google_volume_available"):
        st.warning(
            "Google 검색량 데이터 미활성 (Basic Access 승인 대기 중) — "
            "현재 검색량/KD는 0으로 표시됩니다. 승인되면 자동으로 채워집니다.",
            icon="⚠️",
        )

    st.caption(
        f"총 {meta.get('total', 0)}개 키워드 분석 · 캐시 {meta.get('cached_count', 0)}개 · "
        f"API {meta.get('api_calls', 0)}회 · {meta.get('elapsed_ms', 0)}ms 소요"
    )

    if not gems:
        st.info("보석 키워드(KD ≤ 30 & 검색량 ≥ 1000)가 없습니다. "
                "Basic Access 승인 후 다시 시도하면 채워집니다.")
    else:
        table = []
        for i, g in enumerate(gems, start=1):
            row = {
                "순위": i, "키워드": g.get("keyword", ""),
                "검색량": g.get("volume", 0), "KD": g.get("kd", 0),
                "기회점수": round(g.get("score", 0)),
                "평가": _kd_badge(g.get("kd", 0)),
            }
            if keepa_on:
                row["Amazon"] = len(g.get("amazon_products", []) or [])
            table.append(row)
        st.dataframe(table, width="stretch", hide_index=True)

        if keepa_on:
            with st.expander("🛒 Amazon 상품 상세 (보석별)"):
                for g in gems:
                    prods = g.get("amazon_products", []) or []
                    if not prods:
                        continue
                    st.markdown(f"**💎 {g.get('keyword')}**")
                    st.dataframe(
                        [{"ASIN": p.get("asin"), "BSR": p.get("bsr"),
                          "가격($)": p.get("current_price"), "평점": p.get("rating"),
                          "리뷰": p.get("review_count")} for p in prods],
                        width="stretch", hide_index=True,
                    )

    d1, d2 = st.columns(2)
    d1.download_button("⬇️ 전체 CSV", data=_rows_to_csv(allkw),
                       file_name="keywords_all.csv", mime="text/csv",
                       width="stretch", key="kw_csv_all")
    d2.download_button("⬇️ 보석만 CSV", data=_rows_to_csv(gems),
                       file_name="keywords_gems.csv", mime="text/csv",
                       width="stretch", key="kw_csv_gems",
                       disabled=not gems)


def render() -> None:
    st.title("🔍 키워드 리서치")
    st.caption(
        "Google 검색량 → 보석 키워드 → (선택) Keepa Amazon 소싱. "
        "Node API(server/index.js) 호출."
    )

    payload = _render_input()
    if payload is not None:
        with st.status("분석 중...", expanded=True) as status:
            st.write("① Google Suggest 확장 중...")
            st.write("② 검색량 조회 중...")
            st.write("③ 보석 키워드 필터링...")
            if payload["validate_with_keepa"]:
                st.write("④ Amazon 검증 중 (Keepa)...")
            result = _call_research(payload)
            if result and result.get("success"):
                status.update(label="⑤ 완료!", state="complete", expanded=False)
                st.session_state["kw_result"] = result["data"]
                st.session_state["kw_result_keepa"] = payload["validate_with_keepa"]
            else:
                status.update(label="실패", state="error")

    if st.session_state.get("kw_result"):
        st.divider()
        _render_results(
            st.session_state["kw_result"],
            st.session_state.get("kw_result_keepa", False),
        )

    # Cache stats footer (best-effort).
    try:
        cs = requests.get(CACHE_URL, timeout=5).json()
        if cs.get("success"):
            d = cs["data"]
            st.caption(f"💾 키워드 캐시: {d['total']}개 (만료 {d['expired']}) · hit_rate {d['hit_rate']}")
    except requests.RequestException:
        pass
