"""Page shell shared by every page: header, footer, sidebar pieces, KPI cards, empty states.

Presentation only: no figure is calculated here."""

from __future__ import annotations

import streamlit as st

from app import data

REPO_URL = "https://github.com/pritysapkal/esg-lens-india"
APP_NAME = "ESG Lens India"


def data_caption() -> str:
    years = data.years() if data.available() else []
    span = f"{years[0]} to {years[-1]}" if years else "FY2022-23 to FY2025-26"
    return f"Data: NIFTY 50 + Wipro BRSR filings, {span}"


def page_header(title: str, question: str) -> None:
    """Title, the one question this page answers, and the data caption."""
    st.title(title)
    st.markdown(question)
    st.caption(data_caption())


def footer() -> None:
    st.divider()
    st.caption(
        "FY2025-26 is provisional  ·  Only derived values are shown (intensities, shares, "
        "percentiles, medians, DQS)  ·  Groups with fewer than 5 companies are suppressed"
    )
    st.caption(f"{data.SOURCE_NOTE} {data.DISCLAIMER}")
    st.caption(f"[Project on GitHub]({REPO_URL})")
    sidebar_about()


def sidebar_about() -> None:
    """Last item of the sidebar (page filters come before it, as pages call this at the end)."""
    with st.sidebar.expander("About this project", icon=":material/info:"):
        st.markdown(
            "Comparable figures from the sustainability (BRSR) filings of the NIFTY 50 companies "
            "plus Wipro. Not an ESG rating and not investment advice. "
            f"[Source code and docs]({REPO_URL}). Full details: *About & Methodology*."
        )


def year_filter(years: list[str], label: str = "Financial year") -> str:
    """Sidebar financial-year selector shared across pages (remembered; falls back to the latest
    year in `years`)."""
    current = st.session_state.get("fy")
    index = years.index(current) if current in years else len(years) - 1
    choice = st.sidebar.selectbox(label, years, index=index)
    st.session_state["fy"] = choice
    return choice


def kpi_row(cards: list[tuple], per_row: int = 3) -> None:
    """KPI cards: (label, value, help) tuples in rows of `per_row`; wraps on narrow windows."""
    for start in range(0, len(cards), per_row):
        row = cards[start : start + per_row]
        cols = st.columns(per_row)
        for col, (label, value, *help_text) in zip(cols, row, strict=False):
            with col, st.container(border=True):
                st.metric(label, value, help=help_text[0] if help_text else None)


def not_shown(message: str = "Not shown: fewer than 5 companies in this group.") -> None:
    st.info(message, icon=":material/visibility_off:")
