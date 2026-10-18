"""Methodology: what the numbers are, the publication rule and the limits, in plain English."""

from __future__ import annotations

import streamlit as st

from app import ui

st.title("Methodology")
st.markdown(
    """
### Where the data comes from
Listed Indian companies publish a Business Responsibility and Sustainability Report (BRSR) as a
machine-readable XBRL file. ESG Lens India covers the **NIFTY 50 companies plus Wipro** for
**FY2022-23 to FY2025-26** (196 reports). The files were saved **by hand**: the exchange's terms
forbid automated collection, so nothing here was downloaded by a program.

### What is shown, and what is not
**Only values we calculate are public.** Intensities per Rs crore of turnover, shares, gaps,
medians, ranks, percentiles, the Disclosure Quality Score and counts are shown. Filed values -
tonnes of CO2e, energy, water, turnover, headcounts and filed percentages - are not, and no chart
or table here can be turned back into one. Group statistics need **5 companies or more**;
otherwise they read *n<5 (withheld)*. The reason is reliability: a median of three companies does
not describe a group.

### How to read the figures
- **Whole group vs typical company.** "Whole group" = all emissions of the group divided by all
  its turnover (large companies weigh more). "Typical company" = the median. An average of
  company intensities describes neither, so it is never shown.
- **Provisional.** FY2025-26 has no later report yet. Its figures and scores can still change,
  and its restatements are *not yet observable*.
- **Confirmed changes.** A year-on-year move is ranked only when the next report repeats both
  years' figures. Every move beyond a factor of two in this data turned out to be a data issue.
- **Disclosure Quality Score** (0-100): how completely, consistently and verifiably a company
  discloses in the XBRL file - not how good its ESG performance is. **It is not an ESG rating.**
- **Associations, not causes.** Nothing here says that one thing produces another.

### Limits worth knowing
- Today's NIFTY 50 is applied to all four years (survivorship). Several peer groups have fewer
  than 5 companies, so they are compared within their sector group.
- FY2022-23 is noisy: units were often not filed and had to be inferred.
- Turnover is the only denominator and is in current rupees; inflation alone lowers intensity.
- The score reads only the machine-readable filing; a company may disclose more in its PDF report.
- The statistics are small-sample: with about 50 companies only large effects can be shown.

### Where the details are
In the project repository: `docs/START_HERE.md` (overview), `docs/kpi_definitions.md` (every
KPI), `docs/disclosure_quality_score.md` (the score), `docs/semantic_layer.md` (group figures),
`docs/analysis_findings.md` and `docs/stats_findings.md` (findings), `docs/publication_policy.md`
(what may be published), `docs/ai_analyst.md` (the AI analyst and its guardrails).

### Citing a figure
Cite in plain text, for example: "HDFC Bank Limited, BRSR FY2025-26, filed on NSE (date);
calculated by ESG Lens India". This is not investment advice.
"""
)
ui.footer()
