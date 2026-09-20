"""Entrypoint do Streamlit.

Execute com:  streamlit run app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import streamlit as st

from musicgen.ui.navigation import PAGES, validate

st.set_page_config(
    page_title="MusicGen Local",
    page_icon=":material/graphic_eq:",
    layout="wide",
    initial_sidebar_state="expanded",
)

validate()

st.navigation(
    [
        st.Page(
            spec.view,
            title=spec.title,
            icon=spec.icon,
            default=spec.default,
            **({} if spec.default else {"url_path": spec.url_path}),
        )
        for spec in PAGES
    ]
).run()
