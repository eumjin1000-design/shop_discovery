"""Keepa-related Streamlit UI helpers.

Split from :mod:`app_render` so that file stays under the 300-line hard
limit. Three public entry points:

* :func:`status_cached`   — 30-second cached poll wrapper.
* :func:`badge_html`      — header badge (HTML string).
* :func:`render_sidebar`  — sidebar panel with the time-series chart
                            + manual refresh + auto-backoff status.
"""
from __future__ import annotations

import datetime as _dt

import pandas as pd
import streamlit as st

from modules import keepa_status

# Auto-backoff threshold used elsewhere (modules.sources). Surfaced in the UI
# so the user sees the same number the code is gating on.
BACKOFF_MIN_TOKENS = 5


@st.cache_data(ttl=30, show_spinner=False)
def status_cached() -> dict | None:
    """30-second cache to avoid hammering Keepa on every Streamlit rerun."""
    return keepa_status.get_token_status()


def badge_html() -> str:
    """Header badge (returned as raw HTML for embedding in render_header)."""
    status = status_cached()
    if status is None:
        return (
            '<div style="background:#f5f5f5;color:#999;border-radius:18px;'
            'padding:6px 14px;font-size:12.5px;font-weight:700;white-space:nowrap">'
            '🪙 Keepa: 미설정</div>'
        )
    color = status.get("color", "#999")
    if not status.get("available"):
        text = f"🪙 Keepa: 조회 실패 ({status.get('error') or '?'})"
    else:
        tokens = status["tokensLeft"]
        rate = status["refillRate"]
        next_secs = status["next_refill_secs"]
        label = status["label"]
        if rate:
            text = (
                f"🪙 Keepa Pro · {tokens} 토큰 · {label} "
                f"(+1/{60 // rate}초, 다음 {next_secs}s)"
            )
        else:
            text = f"🪙 Keepa Pro · {tokens} 토큰 · {label}"
    return (
        f'<div style="background:#fff;color:{color};border:1px solid {color};'
        f'border-radius:18px;padding:6px 14px;font-size:12.5px;font-weight:700;'
        f'white-space:nowrap">{text}</div>'
    )


def mock_fallback_expected(estimated_tokens: int) -> bool:
    """True only when Keepa IS configured but tokens are short of the estimate.

    Returns False when Keepa is unconfigured/unreachable — that is the normal
    all-mock mode, not an accidental fallback, so callers should not warn or
    disable on it.
    """
    status = status_cached()
    if status is None or not status.get("available"):
        return False
    return int(status["tokensLeft"]) < int(estimated_tokens)


def preflight_banner(estimated_tokens: int, operation: str) -> None:
    """Show a pre-execution token banner above a Keepa-consuming action.

    Non-blocking — purely informational. The actual protection is the
    auto-backoff in modules.sources (which silently falls back to mock when
    tokens run low). This banner just lets the user *see* it coming so they
    can wait for refill if they want real data instead of mock.

    No-ops when Keepa isn't configured (mock mode = no token concern).
    """
    status = status_cached()
    if status is None or not status.get("available"):
        return  # no key / poll failed → all-mock path, nothing to warn about

    tokens = int(status["tokensLeft"])
    rate = int(status["refillRate"]) or 1
    est = int(estimated_tokens)

    if tokens >= est:
        st.success(
            f"✅ **{operation}** 예상 ~{est} 토큰 · 현재 {tokens} 토큰 — 충분 "
            f"(실 Keepa 데이터 사용)"
        )
        return

    shortfall = est - tokens
    wait_min = shortfall / rate  # tokens needed ÷ tokens/min
    st.warning(
        f"⚠️ **{operation}** 예상 ~{est} 토큰 · 현재 {tokens} 토큰 "
        f"(**{shortfall} 토큰 부족**)\n\n"
        f"지금 실행하면 부족분은 **mock 데이터로 자동 폴백**됩니다. "
        f"실 Keepa 데이터를 원하면 **~{wait_min:.0f}분** 후 재시도하세요 "
        f"(충전 {rate} 토큰/분).",
        icon="⚠️",
    )


def render_sidebar() -> None:
    """Sidebar panel: current state + 1-hour history chart + backoff status."""
    with st.sidebar:
        st.markdown("### 🪙 Keepa 토큰 모니터")
        status = status_cached()

        if status is None:
            st.info("KEEPA_API_KEY 미설정. `.env` 또는 Cloud Secrets에 추가하세요.")
            return
        if not status.get("available"):
            st.error(f"조회 실패: {status.get('error')}")
            return

        tokens = status["tokensLeft"]
        rate = status["refillRate"]
        label = status["label"]
        color = status["color"]
        next_secs = status["next_refill_secs"]

        # Big-number card with traffic-light color.
        st.markdown(
            f'<div style="border:2px solid {color};border-radius:10px;'
            f'padding:10px;text-align:center;background:#fff">'
            f'<div style="color:{color};font-size:32px;font-weight:800">{tokens}</div>'
            f'<div style="color:{color};font-size:13px;font-weight:600">{label}</div>'
            f'<div style="color:#777;font-size:11px;margin-top:4px">'
            f'+1 토큰 / {60 // rate if rate else "?"}초 · 다음 {next_secs}s</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Backoff status.
        backed_off = tokens < BACKOFF_MIN_TOKENS
        if backed_off:
            st.warning(
                f"⚠️ **자동 백오프 발동** — 토큰 < {BACKOFF_MIN_TOKENS} 라 "
                "다음 Keepa 호출은 모두 mock 폴백됩니다. "
                f"~{(BACKOFF_MIN_TOKENS - tokens) * 60}초 후 자동 해제."
            )
        else:
            st.caption(
                f"✅ 정상 운영 (백오프 임계 ≥ {BACKOFF_MIN_TOKENS} 토큰)"
            )

        # 1-hour history line chart.
        history = keepa_status.load_token_history()
        if len(history) >= 2:
            df = pd.DataFrame(history)
            df["time"] = pd.to_datetime(df["ts"], unit="s") + _dt.timedelta(hours=9)
            df = df.set_index("time")[["tokensLeft"]].rename(
                columns={"tokensLeft": "토큰 잔량"}
            )
            st.line_chart(df, height=160)
            st.caption(f"최근 {len(history)}개 폴링 (30s 캐시 기준)")
        else:
            st.caption("히스토리가 충분히 누적되면 차트 표시됨 (몇 번 더 사용 후).")

        if st.button("🔄 캐시 무시 즉시 갱신", width="stretch", key="keepa_refresh"):
            status_cached.clear()
            st.rerun()
