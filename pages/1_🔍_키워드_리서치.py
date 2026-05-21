"""Streamlit multipage entry — Keyword Research.

Thin wrapper: load .env, set page config, delegate to app_keyword_research.
Appears in the sidebar nav automatically (Streamlit native multipage).
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

import app_keyword_research

st.set_page_config(page_title="키워드 리서치", page_icon="🔍", layout="centered")
app_keyword_research.render()
