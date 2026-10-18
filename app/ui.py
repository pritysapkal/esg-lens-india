"""Shared Streamlit pieces: cached access to the public tables, labels, footer, colours."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app import data

# Categorical colours, one per sector group, the same on every page (validated for colour-blind
# separation; the lightest needs visible labels, so every chart also has a table view).
SECTOR_COLOURS = {"Asset-heavy": "#2a78d6", "Asset-light": "#eb6834", "Financials": "#1baf7a"}
NEUTRAL = "#8a8985"
ACCENT = "#2a78d6"


@st.cache_data(show_spinner=False)
def table(name: str) -> pd.DataFrame:
    return data.table(name).copy()


def require_data() -> None:
    if not data.available():
        st.error(
            "The public tables are missing. Run `.\\scripts\\dev.ps1 bi-export` to create "
            "exports/public."
        )
        st.stop()


def provisional_banner(year: str) -> None:
    note = data.provisional_note(year)
    if note:
        st.warning(note, icon=":material/schedule:")


def footer() -> None:
    st.divider()
    st.caption(data.SOURCE_NOTE)
    st.caption(data.DISCLAIMER)


def colour_for(group: str, position: int = 0) -> str:
    fallback = [
        "#2a78d6",
        "#eb6834",
        "#1baf7a",
        "#eda100",
        "#e87ba4",
        "#008300",
        "#6250d6",
        "#e34948",
    ]
    return SECTOR_COLOURS.get(group, fallback[position % len(fallback)])
