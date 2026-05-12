"""Catalog UI for the Shop Discovery GUI: clickable category card grid,
list-management buttons, and the summary stat cards. Presentation only —
selection flows through ``st.session_state["category_input"]``.
"""
from __future__ import annotations

import streamlit as st

from modules import categories, llm

DECISION_COLOR = {"GO": "#2e7d32", "WATCH": "#f9a825", "NO-GO": "#c62828"}

# name-keyword -> emoji (first match wins; fallback 🛒)
_EMOJI = [
    (("pet", "dog", "cat ", "animal"), "🐾"), (("kitchen", "cook", "chef"), "🍳"),
    (("car", "auto", "vehicle"), "🚗"), (("fitness", "gym", "yoga", "workout"), "🏋️"),
    (("led", "light", "lamp"), "💡"), (("phone", "mobile", "case"), "📱"),
    (("baby", "toddler", "kid", "child"), "🍼"), (("skincare", "beauty", "skin", "gua sha", "face"), "💆"),
    (("camp", "outdoor", "hik"), "⛺"), (("eco", "reusable", "sustainab"), "🌱"),
    (("jewel", "necklace", "ring", "accessor"), "💍"), (("photo", "camera", "gimbal"), "📷"),
    (("sleep", "mattress", "pillow", "night"), "😴"), (("desk", "office", "wfh", "work"), "🖥️"),
    (("travel", "luggage", "packing"), "🧳"), (("toy", "montessori", "educational", "learning"), "🧸"),
    (("smart", "iot"), "🏠"), (("garden", "plant"), "🪴"), (("hair", "brush", "comb"), "💇"),
    (("water", "bottle", "fountain", "drink"), "💧"), (("ear", "headphone", "audio"), "🎧"),
    (("glove", "exfoliat", "bath", "shower", "soap"), "🧼"), (("home", "house", "decor"), "🏡"),
]


def category_emoji(name: str) -> str:
    n = name.lower()
    for keys, emoji in _EMOJI:
        if any(k in n for k in keys):
            return emoji
    return "🛒"


def _stars(value: int) -> str:
    return "★" * value + "☆" * (3 - value)


def _badge(decision: str | None) -> str:
    if not decision:
        return '<span style="font-size:11px;color:#aaa">미분석</span>'
    color = DECISION_COLOR.get(decision, "#777")
    return (f'<span style="background:{color};color:#fff;border-radius:10px;'
            f'padding:1px 8px;font-size:11px;font-weight:700">{decision}</span>')


def _card_html(cat, emoji: str, decision: str | None, selected: bool) -> str:
    border = "2px solid #1967d2" if selected else "1px solid #e3e3e3"
    bg = "#eef4fe" if selected else "#ffffff"
    return (
        f'<div style="border:{border};background:{bg};border-radius:10px;'
        f'padding:9px 11px;min-height:104px">'
        f'<div style="display:flex;justify-content:space-between;align-items:center">'
        f'<span style="font-size:22px">{emoji}</span>{_badge(decision)}</div>'
        f'<div style="font-weight:600;font-size:12.5px;line-height:1.25;margin:5px 0 4px">{cat.name}</div>'
        f'<div style="font-size:11px;color:#666">마진 {_stars(cat.margin)} · 수요 {_stars(cat.demand)}</div>'
        f'</div>'
    )


def render_stats(cats, decisions: dict[str, str | None], analyzed: int) -> None:
    go_count = sum(1 for d in decisions.values() if d == "GO")
    items = [("📦 전체 카테고리", len(cats), "#1967d2"),
             ("✅ GO 판정", go_count, "#2e7d32"),
             ("🔬 분석 완료", analyzed, "#6a1b9a")]
    for col, (label, value, color) in zip(st.columns(3), items):
        col.markdown(
            f'<div style="border:1px solid #eee;border-radius:10px;padding:10px 14px;text-align:center">'
            f'<div style="font-size:12px;color:#777">{label}</div>'
            f'<div style="font-size:28px;font-weight:800;color:{color}">{value}</div></div>',
            unsafe_allow_html=True,
        )


def render_manage_buttons() -> None:
    """↩ 이전 목록 복원 · ✨ AI 새목록 · 🎲 랜덤 추천 (side by side)."""
    st.caption(
        "⚠️ **'✨ AI 새목록'** 클릭 시 기존 분석 이력이 초기화됩니다. 직전 목록·이력은 자동 백업되어 "
        "**'↩ 이전 목록 복원'** 으로 되돌릴 수 있습니다."
    )
    b1, b2, b3 = st.columns(3)
    if b1.button("↩ 이전 목록 복원", use_container_width=True, disabled=not categories.has_backup()):
        if categories.restore_previous_list():
            st.session_state.pop("batch", None)
            st.session_state.pop("result", None)
            st.toast("↩ 이전 카테고리 목록으로 복원했습니다.")
            st.rerun()
        else:
            st.warning("복원할 백업이 없습니다.", icon="⚠️")
    if b2.button("✨ AI 새목록", use_container_width=True):
        if not llm.any_available():
            st.warning("LLM API 키가 필요합니다 (GOOGLE_API_KEY 또는 ANTHROPIC_API_KEY).", icon="⚠️")
        else:
            st.warning("생성 시 기존 분석을 초기화합니다. 백업은 자동 저장됩니다.", icon="⚠️")
            with st.spinner("AI(Gemini Flash 우선)로 새 트렌딩 카테고리 20개 생성 중..."):
                gen = categories.generate_new_categories(20, replace=True)
            if gen:
                st.session_state.pop("batch", None)
                st.session_state.pop("result", None)
                st.session_state["category_input"] = ""
                st.toast(f"✨ 새 목록 {len(gen)}개 생성 — 기존 분석 초기화, 백업 저장 완료")
                st.rerun()
            else:
                st.warning("새 카테고리를 받지 못했습니다. 잠시 후 다시 시도하세요.", icon="⚠️")
    if b3.button("🎲 랜덤 추천", use_container_width=True):
        rc = categories.random_category()
        st.session_state["category_input"] = rc.name
        st.toast(f"🎲 추천: {rc.name}")
        st.rerun()


def render_category_grid(cats, decisions: dict[str, str | None], selected: str, cols: int = 5) -> None:
    """Card grid; clicking a card's button selects that category."""
    for start in range(0, len(cats), cols):
        for col, cat in zip(st.columns(cols), cats[start:start + cols]):
            with col:
                is_sel = cat.name == selected
                st.markdown(_card_html(cat, category_emoji(cat.name),
                                       decisions.get(cat.name), is_sel),
                            unsafe_allow_html=True)
                if st.button("✓ 선택됨" if is_sel else "선택", key=f"pick::{cat.name}",
                             use_container_width=True, type="secondary"):
                    st.session_state["category_input"] = cat.name
                    st.rerun()
