"""Concentration: how few companies carry most of the Scope 1+2 emissions (shares only)."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from app import data, layout, ui
from app import format as fmt

ui.require_data()
frame = ui.table("rpt_public_concentration")

layout.page_header(
    "Concentration of emissions",
    "**How few companies carry most of the emissions?** Each company's share of the **Scope 1+2 emissions of all companies covered** in a year, from "
    "the largest emitter down, and the running total (a Pareto chart). Shares only: the tonnes "
    "behind them are filed values and are not published.",
)
year = layout.year_filter(data.years())
ui.provisional_banner(year)

rows = frame[frame["fiscal_year_label"] == year].sort_values("emitter_rank")
if rows.empty:
    layout.not_shown("Not shown: no emissions shares are published for this year.")
    ui.footer()
    st.stop()
by_rank = rows.set_index("emitter_rank")["cumulative_share_pct"]
layout.kpi_row(
    [
        ("Largest emitter (% of total)", fmt.pct(by_rank.get(1)), "Share of the year's Scope 1+2 emissions."),
        ("Top 5 (% of total)", fmt.pct(by_rank.get(5)), "Combined share of the five largest emitters."),
        ("Top 10 (% of total)", fmt.pct(by_rank.get(10)), "Combined share of the ten largest emitters."),
        ("Companies for 80% of emissions",
         f"{int((rows['cumulative_share_pct'] < 80).sum()) + 1} of {len(rows)}",
         "Fewest companies whose shares add up to 80%."),
    ],
    per_row=4,
)  # fmt: skip

shown = rows.head(15)
figure = go.Figure()
figure.add_trace(
    go.Bar(
        x=shown["display_name"], y=shown["share_of_total_pct"], name="Share of total emissions",
        marker={"color": [ui.colour_for(s) for s in shown["sector_group"]], "cornerradius": 4},
        customdata=shown[["emitter_rank", "sector_group"]],
        hovertemplate="#%{customdata[0]} %{x} (%{customdata[1]})<br>share %{y:.1f}%<extra></extra>",
    )
)  # fmt: skip
figure.add_trace(
    go.Scatter(
        x=shown["display_name"], y=shown["cumulative_share_pct"], name="Cumulative share",
        mode="lines+markers", line={"color": ui.NEUTRAL, "width": 2}, marker={"size": 8},
        hovertemplate="%{x}: cumulative %{y:.1f}%<extra></extra>",
    )
)  # fmt: skip
figure.add_hline(y=80, line={"color": ui.NEUTRAL, "dash": "dot", "width": 1}, annotation_text="80%")
figure.update_layout(height=460, margin={"l": 0, "r": 10, "t": 10, "b": 10}, xaxis={"title": "Company (largest emitter first)"}, yaxis={"title": "% of the year's Scope 1+2 emissions", "range": [0, 105]},
                     legend={"orientation": "h", "y": -0.35}, bargap=0.25)  # fmt: skip
st.plotly_chart(ui.readable(figure), width="stretch")
st.caption(
    "Bar colour = sector group: blue Asset-heavy, orange Asset-light, green Financials. The 15 largest emitters are drawn."
)

with st.expander("Table: every company that year"):
    st.dataframe(
        rows[["emitter_rank", "display_name", "sector_group", "share_of_total_pct", "cumulative_share_pct"]].rename(
            columns={"emitter_rank": "Rank", "display_name": "Company", "sector_group": "Sector group",
                     "share_of_total_pct": "Share (%)", "cumulative_share_pct": "Cumulative (%)"}
        ),
        hide_index=True, width="stretch",
    )  # fmt: skip
st.caption(
    "'Total' means the companies in this project (NIFTY 50 plus Wipro), not India. Scope 1+2 only."
)
ui.footer()
