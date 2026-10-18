"""Plain-English labels for the report card and the AI analyst. tests/test_app.py checks that
GROUP_METRICS agrees with the KPI catalogue seed (label source and the company count that
gates each statistic)."""

from __future__ import annotations

import math

import pandas as pd

# Published group metrics of rpt_public_group_metrics:
# column -> (label, unit, companies column that gates it or None for a count, is a restatement figure)
GROUP_METRICS: dict[str, tuple[str, str, str | None, bool]] = {
    "ghg_intensity_agg": ("GHG intensity, whole group", "tCO2e per Rs crore", "companies_with_ghg_intensity", False),
    "ghg_intensity_median": ("GHG intensity, typical company", "tCO2e per Rs crore", "companies_with_ghg_intensity", False),
    "energy_intensity_agg": ("Energy intensity, whole group", "GJ per Rs crore", "companies_with_energy_intensity", False),
    "energy_intensity_median": ("Energy intensity, typical company", "GJ per Rs crore", "companies_with_energy_intensity", False),
    "water_intensity_agg": ("Water intensity, whole group", "kl per Rs crore", "companies_with_water_intensity", False),
    "water_intensity_median": ("Water intensity, typical company", "kl per Rs crore", "companies_with_water_intensity", False),
    "waste_intensity_agg": ("Waste intensity, whole group", "t per Rs crore", "companies_with_waste_intensity", False),
    "waste_intensity_median": ("Waste intensity, typical company", "t per Rs crore", "companies_with_waste_intensity", False),
    "renewable_share_agg": ("Renewable share of energy, whole group", "%", "companies_with_renewable_share", False),
    "female_workforce_agg": ("Women in workforce, whole group", "%", "companies_with_female_workforce", False),
    "scope3_disclosed_share": ("Companies disclosing Scope 3", "%", "companies_reporting", False),
    "dqs_avg": ("Disclosure Quality Score, average", "points (0-100)", "companies_with_dqs", False),
    "dqs_median": ("Disclosure Quality Score, typical company", "points (0-100)", "companies_with_dqs", False),
    "dqs_grade_a_share": ("Company-years graded A", "%", "companies_with_dqs_grade", False),
    "voluntary_depth_avg": ("Voluntary depth, average", "share (0-1)", "companies_with_voluntary_depth", False),
    "material_restatement_share": ("Figures materially restated", "%", "companies_with_compared_restatements", True),
    "companies_reporting": ("Companies reporting", "companies", None, False),
    "material_restatements": ("Material restatements", "restated values", None, True),
}  # fmt: skip

GROUP_TYPES = {
    "all": "All companies",
    "sector_group": "Sector group",
    "peer_group": "Peer group",
    "ranking_group": "Ranking group",
    "size_band": "Size band",
    "ownership_type": "Ownership",
}

REASON_CODES = {
    "missing_required_metrics": "Some mandatory metrics were not filed",
    "low_voluntary_disclosure": "Few voluntary (Leadership) indicators answered",
    "waste_balance_gap": "Waste figures do not add up",
    "waste_recovery_over_100": "Waste recovered exceeds waste generated",
    "implausible_zero": "A zero that cannot be right",
    "unit_inconsistency": "A unit had to be corrected",
    "suspected_scale_error": "A value was far off the next report (a unit slip)",
    "material_restatement": "The next report changed figures materially",
    "unexplained_yoy_anomaly": "A jump against the year before with no recorded event",
    "assurance_core_only": "Only the mandatory BRSR Core was assured",
    "assessment_not_assurance": "A third-party assessment instead of assurance",
    "limited_assurance": "Limited assurance only",
    "no_assurance": "Nothing marked as assured",
}

RANKING_STATUS = {
    "not_material": "not ranked for this group (not material)",
    "group_n_lt_5": "not ranked: fewer than 5 companies (n<5)",
    "flagged_value": "not ranked: value flagged",
    "no_direction": "not ranked: no better or worse direction",
    "no_group": "not ranked: no group",
}

CONFIDENCE = {
    "confirmed": "confirmed by the next report",
    "provisional": "provisional (latest year, not confirmed yet)",
    "inferred_unit": "unconfirmed: unit inferred from the next report",
    "restated_later": "unconfirmed: restated in the next report",
    "one_year_reversal": "unconfirmed: one-year reversal (likely a filing slip)",
    "not_confirmed": "unconfirmed: nothing to check against",
}


def is_missing(value) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value)) or value is pd.NA


def group_cell(row: pd.Series, metric: str):
    """A group figure as shown: the number, or why it is empty."""
    value = row.get(metric)
    if not is_missing(value):
        return value
    _label, _unit, gate, restatement = GROUP_METRICS[metric]
    reason = row.get("suppressed_reason") or ""
    if restatement and "not_yet_observable" in reason:
        return "not yet observable"
    if gate and not is_missing(row.get(gate)) and row.get(gate) < 5:
        return "n<5 (withheld)"
    return "-"


def ranking_status(is_ranked, reason) -> str:
    if bool(is_ranked):
        return "ranked"
    return RANKING_STATUS.get(reason or "", "not ranked")


def reason_codes(codes: str | None) -> list[str]:
    if is_missing(codes) or not codes:
        return []
    return [REASON_CODES.get(code, code) for code in str(codes).split("|") if code]


def fmt(value, digits: int = 1, suffix: str = "") -> str:
    if isinstance(value, str):
        return value
    if is_missing(value):
        return "-"
    return f"{value:,.{digits}f}{suffix}"


# The 19 KPIs with a peer position (rpt_public_company_percentile): label and pillar.
# Environment / Social / Governance, as BRSR groups its principles; tests/test_app.py checks
# that every KPI of the public table is here.
KPI_INFO: dict[str, tuple[str, str]] = {
    "ghg_intensity_tco2e_per_cr": ("GHG intensity (Scope 1+2 per Rs crore)", "Environment"),
    "energy_intensity_gj_per_cr": ("Energy intensity (GJ per Rs crore)", "Environment"),
    "renewable_share_pct": ("Renewable share of energy (%)", "Environment"),
    "water_intensity_kl_per_cr": ("Water intensity (kl per Rs crore)", "Environment"),
    "waste_intensity_t_per_cr": ("Waste intensity (t per Rs crore)", "Environment"),
    "waste_recovery_rate_pct": ("Waste recovery rate (%)", "Environment"),
    "female_workforce_pct": ("Women in workforce (%)", "Social"),
    "female_wage_share_pct": ("Women share of gross wages (%)", "Social"),
    "pay_equity_gap_pp": ("Pay equity gap (pp)", "Social"),
    "attrition_gap_pp": ("Attrition gap (pp)", "Social"),
    "ltifr_employees": ("LTIFR, employees", "Social"),
    "ltifr_workers": ("LTIFR, workers", "Social"),
    "fatalities_per_10k_workforce": ("Fatalities per 10,000 workforce", "Social"),
    "wellbeing_cost_pct_revenue": ("Well-being spend (% of revenue)", "Social"),
    "posh_complaints_pct_female": ("POSH complaints (% of female staff)", "Social"),
    "msme_sourcing_pct": ("Sourcing from MSMEs (%)", "Governance"),
    "days_payable": ("Days of accounts payable", "Governance"),
    "rpt_purchases_pct": ("Purchases from related parties (%)", "Governance"),
    "rpt_sales_pct": ("Sales to related parties (%)", "Governance"),
}
PILLARS = ("Environment", "Social", "Governance")

# Every column name that can reach a table on any page -> what the reader sees.
FRIENDLY_COLUMNS = {
    "group": "Group",
    "group_value": "Group",
    "group_key": "Group",
    "year": "Financial year",
    "fiscal_year_label": "Financial year",
    "value": "Value",
    "status": "Shown as",
    "companies_behind_it": "Companies behind it",
    "kpi": "KPI",
    "kpi_label": "KPI",
    "ranking_group": "Ranking group",
    "sector_group": "Sector group",
    "percentile_in_group": "Percentile (100 = best)",
    "rank_in_group": "Rank (1 = best)",
    "companies_in_group": "Companies in group",
    "n_in_group": "Companies in group",
    "ranking_status": "Ranking",
    "value_if_public": "Value (computed KPIs only)",
    "kpi_value_public": "Value (computed KPIs only)",
    "emitter_rank": "Rank",
    "display_name": "Company",
    "share_of_total_pct": "Share of emissions (%)",
    "cumulative_share_pct": "Cumulative share (%)",
    "from_year": "From",
    "to_year": "To",
    "intensity_from": "Intensity before",
    "intensity_to": "Intensity after",
    "change_pct": "Change (%)",
    "level": "Level",
    "n_pairs": "Figures compared",
    "n_material": "Restated materially",
    "pct_material": "Restated materially (%)",
    "n_material_flattering": "Of those, flattering",
    "pct_material_flattering": "Flattering (% of restated)",
    "n_companies": "Companies",
    "n_companies_with_material": "Companies with a restatement",
}


def friendly(frame: pd.DataFrame) -> pd.DataFrame:
    """The same table with reader-facing column names (unknown names: underscores to spaces)."""

    def name(column) -> str:
        column = str(column)
        if column in FRIENDLY_COLUMNS:
            return FRIENDLY_COLUMNS[column]
        if "_" not in column:  # already a heading written for readers
            return column
        text = column.replace("_", " ")
        return text[:1].upper() + text[1:]

    return frame.rename(columns=name)
