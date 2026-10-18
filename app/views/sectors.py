"""Sectors: published group figures by group and year; withheld figures say why."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from app import labels, ui

ui.require_data()
groups = ui.table("rpt_public_group_metrics")

st.title("Sectors and groups")
st.markdown(
    "**Whole group** = all of the group's emissions (or energy, water, waste) divided by all its "
    "turnover: large companies weigh more. **Typical company** = the median company. A figure is "
    "shown only when **5 or more companies** stand behind it; otherwise it reads *n<5 (withheld)*."
)
metric_names = [m for m in labels.GROUP_METRICS if labels.GROUP_METRICS[m][2] is not None]
left, right = st.columns(2)
group_type = left.selectbox(
    "Group by", [g for g in labels.GROUP_TYPES if g != "all"], format_func=labels.GROUP_TYPES.get
)
metric = right.selectbox("Figure", metric_names, format_func=lambda m: labels.GROUP_METRICS[m][0])
label, unit, gate, _restatement = labels.GROUP_METRICS[metric]

rows = groups[groups["group_type"].isin([group_type, "all"])].copy()
rows["shown"] = [labels.group_cell(row, metric) for _, row in rows.iterrows()]
wide = rows.pivot(index="group_value", columns="fiscal_year_label", values="shown")
order = [g for g in sorted(wide.index) if g != "All companies"] + ["All companies"]
wide = wide.reindex(order)
digits = 1 if unit in ("%", "points (0-100)") else 2
st.markdown(f"**{label}** ({unit})")
st.dataframe(wide.map(lambda v: labels.fmt(v, digits)), width="stretch")
st.caption(
    "FY2025-26 is provisional. Restatement figures of FY2025-26 are not yet observable: the next report does not exist yet."
)

numeric = rows[rows["shown"].map(lambda v: not isinstance(v, str))]
if not numeric.empty:
    figure = go.Figure()
    for position, (group, frame) in enumerate(numeric.groupby("group_value")):
        frame = frame.sort_values("fiscal_year_label")
        colour = ui.NEUTRAL if group == "All companies" else ui.colour_for(group, position)
        figure.add_trace(
            go.Scatter(
                x=frame["fiscal_year_label"], y=frame["shown"].astype(float), name=group, mode="lines+markers",
                line={"width": 2, "color": colour, "dash": "dot" if group == "All companies" else "solid"},
                marker={"size": 8}, hovertemplate=f"{group}<br>%{{x}}: %{{y:,.{digits}f}} {unit}<extra></extra>",
            )
        )  # fmt: skip
    figure.update_layout(height=420, margin={"l": 0, "r": 10, "t": 10, "b": 10}, hovermode="x unified",
                         yaxis={"title": unit}, legend={"orientation": "h", "y": -0.15})  # fmt: skip
    if metric.startswith(("ghg_", "energy_", "water_", "waste_")):
        figure.update_yaxes(type="log", title=f"{unit} (log scale)")
    st.plotly_chart(figure, width="stretch")
    withheld = rows[rows["shown"].map(lambda v: isinstance(v, str) and v.startswith("n<5"))]
    if not withheld.empty:
        st.caption(
            "Not drawn (fewer than 5 companies): "
            + ", ".join(
                f"{g} {y}"
                for g, y in zip(withheld["group_value"], withheld["fiscal_year_label"], strict=True)
            )
        )

with st.expander("Companies behind each figure"):
    counts = groups[groups["group_type"].isin([group_type, "all"])].pivot(
        index="group_value", columns="fiscal_year_label", values=gate
    )
    st.dataframe(counts.reindex(order).astype("Int64"), width="stretch")
st.caption("Source table: rpt_public_group_metrics.")
ui.footer()
