"""Overview: what is covered, six headline figures and five insights, all from the public tables."""

from __future__ import annotations

import streamlit as st

from app import data, labels, layout, ui
from app import format as fmt

ui.require_data()
latest, final = data.latest_year(), data.latest_final_year()
year = layout.year_filter(data.years())
# restatements of a provisional year cannot be observed yet: its card shows the latest final year
restated_year = final if data.is_provisional(year) else year

layout.page_header(
    "ESG Lens India - public report card",
    "**What do the BRSR filings of the NIFTY 50 companies plus Wipro say, in comparable figures?** "
    "Intensities, shares, peer positions and a score for how well each company discloses. Every "
    "figure here is calculated by ESG Lens India; filed values such as tonnes or rupees are never "
    "shown.",
)

overall = data.group_row("all", "All companies", year)
overall_final = data.group_row("all", "All companies", restated_year)
concentration = ui.table("rpt_public_concentration")
in_year = concentration[concentration["fiscal_year_label"] == year].set_index("emitter_rank")
latest_conc = concentration[concentration["fiscal_year_label"] == latest].set_index("emitter_rank")

st.subheader(f"{year} at a glance")
ui.provisional_banner(year)
layout.kpi_row(
    [
        ("Companies reporting", fmt.count(overall["companies_reporting"]),
         "Companies with a BRSR filing in the year."),
        ("GHG intensity, whole group (tCO2e per Rs crore)",
         fmt.intensity(labels.group_cell(overall, "ghg_intensity_agg")),
         "Scope 1+2 tCO2e per Rs crore of turnover, whole group (sum over sum)."),
        ("Disclosure score, typical company (0-100)",
         fmt.score(labels.group_cell(overall, "dqs_median")),
         "Median Disclosure Quality Score (0-100). Not an ESG rating."),
        ("Reports with Scope 3 (%)",
         labels.fmt(labels.group_cell(overall, "scope3_disclosed_share"), 0, "%"),
         "Share of reports that disclose Scope 3 emissions."),
        ("Emissions held by top 5 companies (%)",
         fmt.pct(in_year.loc[5, "cumulative_share_pct"], 1),
         "Share of the Scope 1+2 emissions of all companies covered."),
        (f"Figures restated, {restated_year} (%)",
         fmt.pct(labels.group_cell(overall_final, "material_restatement_share"), 1),
         f"Share of {restated_year} figures changed materially in the next report. "
         f"{latest} is not observable yet."),
    ],
    per_row=3,
)  # fmt: skip

# ------------------------------------------------------------------ five insights
st.subheader("Five things the data says")

top1 = latest_conc.loc[1, "cumulative_share_pct"]
top5 = latest_conc.loc[5, "cumulative_share_pct"]
heavy = data.group_row("sector_group", "Asset-heavy", latest)
agg, median = heavy["ghg_intensity_agg"], heavy["ghg_intensity_median"]
yoy = ui.table("rpt_public_ghg_yoy")
ranked = yoy[yoy["is_ranked"].astype(bool)]
best = ranked.sort_values("change_pct").iloc[0] if not ranked.empty else None
worst = ranked.sort_values("change_pct").iloc[-1] if not ranked.empty else None
restatements = ui.table("rpt_public_restatement_summary")
overall_restated = restatements[restatements["level"] == "overall"].iloc[0]
final_row = data.group_row("all", "All companies", final)

insights = [
    (
        "A handful of companies carry most of the emissions",
        f"In {latest} the five largest emitters hold {fmt.pct(top5)} of the "
        f"Scope 1+2 emissions of all companies covered, and the largest alone {fmt.pct(top1)}. Any "
        "'average' trend of this set is the trend of a few companies.",
    ),
    (
        "Heavy industry has two honest intensity figures",
        f"Asset-heavy companies as a whole emit {fmt.intensity(agg)} tCO2e per Rs crore of turnover; the "
        f"typical company {fmt.intensity(median)}. A few very carbon-heavy businesses set the first, the many "
        "set the second. Neither is an average of company ratios.",
    ),
    (
        "The biggest year-on-year moves are data problems",
        (
            f"Counting only changes a later report confirms, the largest improvement in GHG intensity "
            f"is {best['display_name']} ({best['change_pct']:+.1f}%, {best['from_year']} to {best['to_year']}) "
            f"and the largest deterioration {worst['display_name']} ({worst['change_pct']:+.1f}%). "
            f"{len(yoy) - len(ranked)} of {len(yoy)} changes are not ranked: provisional, an inferred unit, "
            "restated later or a one-year reversal."
        )
        if best is not None
        else "No year-on-year change is confirmed yet.",
    ),
    (
        "Restated figures are common and not tilted in the companies' favour",
        f"{fmt.pct(overall_restated['pct_material'])} of the figures that can be checked against the next "
        "report were changed materially. Of those with a direction, about half make the trend look "
        "better - the Week 11 test found no tilt (47.7%, interval 41.5% to 54.0%).",
    ),
    (
        "Disclosure quality is high and even, and says nothing about carbon",
        f"The typical company scores {fmt.score(final_row['dqs_median'])} of 100 in {final}, and "
        f"{labels.fmt(final_row['dqs_grade_a_share'], 0, '%')} of graded reports reach grade A. The Week 11 test found "
        "no association between the score and carbon intensity - the score says how far the numbers "
        "can be trusted, not whether they are good.",
    ),
]
for number, (title, text) in enumerate(insights, start=1):
    with st.container(border=True):
        st.markdown(f"**{number}. {title}**")
        st.markdown(text)

st.caption(
    "Group figures are shown only for 5 companies or more. Findings in full: docs/analysis_findings.md "
    "and docs/stats_findings.md in the project repository."
)
ui.footer()
