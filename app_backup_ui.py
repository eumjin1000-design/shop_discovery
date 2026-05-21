"""Backup / restore UI — protects data across app updates (Cloud redeploys).

Three controls in one expander:
  ↩ 이전 목록 복원      — in-app *.bak.json restore (same as 카테고리 목록 헤더)
  💾 전체 백업 다운로드  — bundle all state into one JSON file
  📤 백업 파일 복원      — re-upload that JSON to fully restore

The download/upload pair is the only mechanism that survives a fresh
Streamlit Cloud container (where gitignored *.json files are wiped).
"""
from __future__ import annotations

import json

import streamlit as st

from modules import categories
from modules.timez import stamp as kst_stamp


def render_backup_section() -> None:
    """Render the backup/restore expander. Safe to call once per page."""
    with st.expander("🗂️ 데이터 백업 / 복원 (앱 업데이트 후 복구)"):
        st.caption(
            "앱 업데이트(재배포) 시 분석 이력·AI 목록이 사라질 수 있습니다. "
            "**전체 백업 다운로드**로 파일을 보관하고, 업데이트 후 **백업 파일 복원**으로 되돌리세요."
        )

        # 1) In-app previous-list restore (mirrors the category-list header).
        if st.button("↩ 이전 목록 복원", width="stretch", key="bk_restore_prev",
                     disabled=not categories.has_backup(),
                     help="직전 'AI 새목록' 생성 전 상태로 되돌립니다 (*.bak.json)."):
            if categories.restore_previous_list():
                st.session_state.pop("batch_rows", None)
                st.session_state.pop("result", None)
                st.toast("↩ 이전 카테고리 목록으로 복원했습니다.")
                st.rerun()
            else:
                st.warning("복원할 백업이 없습니다.", icon="⚠️")

        c_dl, c_up = st.columns(2)

        # 2) Full-state download (survives redeploys).
        bundle = json.dumps(categories.export_all_state(),
                            ensure_ascii=False, indent=2).encode("utf-8")
        c_dl.download_button(
            "💾 전체 백업 다운로드", data=bundle,
            file_name=f"shop_discovery_backup_{kst_stamp()}.json",
            mime="application/json", width="stretch", key="bk_download",
        )

        # 3) Full-state restore from uploaded file.
        up = c_up.file_uploader("📤 백업 파일 복원", type=["json"],
                                key="bk_upload", label_visibility="visible")
        if up is not None and st.button("📤 이 파일로 복원 실행",
                                        width="stretch", key="bk_restore_file"):
            try:
                data = json.loads(up.read().decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                st.error("유효한 백업 JSON이 아닙니다.", icon="⚠️")
                return
            if categories.import_all_state(data):
                st.session_state.pop("batch_rows", None)
                st.session_state.pop("result", None)
                exported = data.get("exported_at", "?")
                st.success(f"✅ 백업 복원 완료 (백업 시점: {exported}). 새로고침합니다.")
                st.rerun()
            else:
                st.error("백업 형식이 올바르지 않습니다 (version 필드 누락).", icon="⚠️")
