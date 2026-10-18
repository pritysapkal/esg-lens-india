"""Company report card: one company in one year, placed among its peers."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app import data, labels, ui

ui.require_data()
companies = data.companies()
dqs = ui.table("rpt_public_disclosure_quality")
company_year = ui.table("rpt_public_company_year")
percentiles = ui.table("rpt_public_company_percentile")

st.title("Company report card")
left, right = st.columns([2, 1])
name = left.selectbox("Company", companies["display_name"].tolist())
company = companies[companies["display_name"] == name].iloc[0]
company_years = sorted(
    company_year.loc[company_year["isin"] == company["isin"], "fiscal_year_label"].unique()
)
year = right.selectbox("Financial year", company_years, index=len(company_years) - 1)

st.caption(
    f"{company['symbol']} - {company['sector_group']}, peer group {company['peer_group']}; ranked "
    f"within **{company['ranking_group']}**."
)
ui.provisional_banner(year)

score = dqs[(dqs["isin"] == company["isin"]) & (dqs["fiscal_year_label"] == year)]
kpis = company_year[
    (company_year["isin"] == company["isin"]) & (company_year["fiscal_year_label"] == year)
]

# ------------------------------------------------------------------ disclosure quality
st.subheader("Disclosure Quality Score")
if score.empty:
    st.info("No score for this year.")
else:
    s = score.iloc[0]
    status = "Provisional" if bool(s["is_provisional"]) else "Final"
    cols = st.columns(4)
    cols[0].metric(
        "Score (0-100)",
        labels.fmt(s["dqs_total"], 1),
        help=f"{status}. Compare within one year only.",
    )
    cols[1].metric("Grade", s["dqs_grade"] or "-")
    rank = (
        "-"
        if labels.is_missing(s["dqs_rank_in_group"])
        else f"{int(s['dqs_rank_in_group'])} of {int(s['dqs_group_n'])}"
    )
    cols[2].metric(
        "Rank in group",
        rank,
        help="1 = best in the ranking group and year; only with 5 or more gradable companies.",
    )
    cols[3].metric(
        "Percentile in group", labels.fmt(s["dqs_percentile_in_group"], 0), help="100 = best."
    )

    parts = pd.DataFrame(
        {
            "Part": ["Completeness (mandatory and voluntary)", "Mandatory completeness", "Voluntary depth",
                     "Internal consistency", "Temporal consistency", "Assurance"],
            "Score (0-1)": [s["dqs_completeness"], s["dqs_mandatory_completeness"], s["dqs_voluntary_depth"],
                            s["dqs_internal_consistency"], s["dqs_temporal_consistency"], s["dqs_assurance"]],
        }
    )  # fmt: skip
    parts["Score (0-1)"] = parts["Score (0-1)"].map(
        lambda v: "not scored this year" if labels.is_missing(v) else f"{v:.2f}"
    )
    a, b = st.columns(2)
    a.dataframe(parts, hide_index=True, width="stretch")
    reasons = labels.reason_codes(s["dqs_reason_codes"])
    with b:
        st.markdown("**Where points were lost**")
        st.markdown("\n".join(f"- {r}" for r in reasons) if reasons else "No points lost.")
        st.markdown(
            f"**Assurance:** {s['assurance_level'] or 'not stated'}"
            + (f", scope {s['assurance_scope']}" if s["assurance_scope"] else "")
        )
    if bool(s["is_provisional"]):
        st.caption(
            "Provisional: the check against the next report cannot run yet, so this score can still fall."
        )

# ------------------------------------------------------------------ intensities against peers
st.subheader("Against its peers")
group = data.group_row("ranking_group", company["ranking_group"], year)
rows = []
for column, metric, label in (
    ("ghg_intensity_tco2e_per_cr", "ghg_intensity_median", "GHG intensity (tCO2e per Rs crore)"),
    ("energy_intensity_gj_per_cr", "energy_intensity_median", "Energy intensity (GJ per Rs crore)"),
    ("water_intensity_kl_per_cr", "water_intensity_median", "Water intensity (kl per Rs crore)"),
    ("waste_intensity_t_per_cr", "waste_intensity_median", "Waste intensity (t per Rs crore)"),
):
    value = kpis.iloc[0][column] if not kpis.empty else None
    median = labels.group_cell(group, metric) if group is not None else "-"
    position = percentiles[
        (percentiles["isin"] == company["isin"])
        & (percentiles["fiscal_year_label"] == year)
        & (percentiles["kpi_name"] == column)
    ]
    status = (
        labels.ranking_status(position.iloc[0]["is_ranked"], position.iloc[0]["reason_not_ranked"])
        if not position.empty
        else "no value"
    )
    rows.append(
        {
            "KPI": label,
            "Company": labels.fmt(value, 2),
            "Typical company of the group": labels.fmt(median, 2),
            "Ranking": status,
        }
    )
st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

positions = percentiles[
    (percentiles["isin"] == company["isin"]) & (percentiles["fiscal_year_label"] == year)
].copy()
positions["Ranking"] = [
    labels.ranking_status(r, why)
    for r, why in zip(positions["is_ranked"], positions["reason_not_ranked"], strict=True)
]
ranked = positions[positions["is_ranked"].astype(bool)].sort_values("percentile_in_group")
if not ranked.empty:
    st.markdown(f"**Percentile in {company['ranking_group']}** (100 = best in the group)")
    figure = go.Figure(
        go.Bar(
            x=ranked["percentile_in_group"],
            y=ranked["kpi_label"],
            orientation="h",
            marker={"color": ui.ACCENT, "cornerradius": 4},
            text=ranked["percentile_in_group"].map(lambda v: f"{v:.0f}"),
            textposition="outside",
            hovertemplate="%{y}: percentile %{x:.1f}<extra></extra>",
        )
    )
    figure.add_vline(x=50, line={"color": ui.NEUTRAL, "dash": "dot", "width": 1})
    figure.update_layout(height=40 + 32 * len(ranked), margin={"l": 0, "r": 30, "t": 10, "b": 30},
                         xaxis={"range": [0, 108], "title": "percentile (100 = best)"}, yaxis={"title": None})  # fmt: skip
    st.plotly_chart(figure, width="stretch")
with st.expander("All KPIs: percentile, rank and why a KPI is not ranked"):
    st.dataframe(
        positions[["kpi_label", "percentile_in_group", "rank_in_group", "n_in_group", "Ranking", "kpi_value_public"]]
        .rename(columns={"kpi_label": "KPI", "percentile_in_group": "Percentile", "rank_in_group": "Rank",
                         "n_in_group": "Companies in group", "kpi_value_public": "Value (computed KPIs only)"}),
        hide_index=True, width="stretch",
    )  # fmt: skip
    st.caption(
        "Filed values (for example a filed percentage) are not public, so their value column stays empty; the position is ours and is shown."
    )
ui.footer()
