"""Shared Streamlit pieces: cached access to the public tables, labels, footer, colours."""

from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

from app import data, layout

# Categorical colours, one per sector group, the same on every page (validated for colour-blind
# separation; the lightest needs visible labels, so every chart also has a table view).
SECTOR_COLOURS = {"Asset-heavy": "#2a78d6", "Asset-light": "#eb6834", "Financials": "#1baf7a"}
NEUTRAL = "#8a8985"
ACCENT = "#1f7a6d"  # the theme's primary colour (.streamlit/config.toml)
# better / worse half of a ranking group: blue and orange, validated colour-blind safe as a pair
# (dataviz validator: CVD separation 24.7, contrast >= 3:1); every bar also carries its number
BETTER = "#2a78d6"
WORSE = "#eb6834"
CHART_FONT_SIZE = 14  # readable at normal zoom; Plotly's default is 12


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
    layout.footer()


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


# Every chart of the app: readable text at normal zoom, quiet grid.
TEXT = "#1f2a28"
GRID = "#e3e7e4"
pio.templates["esg_lens"] = go.layout.Template(
    layout={
        "font": {"size": CHART_FONT_SIZE, "color": TEXT},
        "colorway": [SECTOR_COLOURS["Asset-heavy"], SECTOR_COLOURS["Asset-light"], SECTOR_COLOURS["Financials"], ACCENT],
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "hoverlabel": {"font": {"size": CHART_FONT_SIZE}, "bgcolor": "white", "bordercolor": GRID},
        "legend": {"font": {"size": CHART_FONT_SIZE}},
        "xaxis": {
            "tickfont": {"size": CHART_FONT_SIZE},
            "title": {"font": {"size": CHART_FONT_SIZE}},
            "showgrid": False, "linecolor": GRID, "zeroline": False,
        },
        "yaxis": {
            "tickfont": {"size": CHART_FONT_SIZE},
            "title": {"font": {"size": CHART_FONT_SIZE}},
            "gridcolor": GRID, "zeroline": False,
        },
    }
)  # fmt: skip
pio.templates.default = "plotly+esg_lens"


def log_ticks(values) -> dict:
    """Tick positions and labels for a log axis: powers of ten written as 0.1 / 1 / 10 / 100 / 1,000."""
    positive = [float(v) for v in values if v is not None and float(v) > 0]
    if not positive:
        return {}
    low = math.floor(math.log10(min(positive)))
    high = math.ceil(math.log10(max(positive)))
    ticks = [10.0**p for p in range(low, high + 1)]
    return {"tickvals": ticks, "ticktext": [f"{t:,.0f}" if t >= 1 else f"{t:g}" for t in ticks]}


def readable(figure: go.Figure) -> go.Figure:
    """Set the text sizes on the figure itself: Streamlit's chart theme overrides template fonts,
    which left axis labels at 12 px."""
    size = {"size": CHART_FONT_SIZE}
    figure.update_layout(font=size, legend={"font": size}, hoverlabel={"font": size})
    figure.update_xaxes(tickfont=size, title_font=size)
    figure.update_yaxes(tickfont=size, title_font=size)
    figure.update_traces(textfont=size, selector={"type": "bar"})
    return figure
