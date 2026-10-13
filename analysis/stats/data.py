"""Read the gold tables for the statistics studies. Only this module holds SQL.

The "confirmed" rules are those of the Week 10 analysis (analysis/sql/q03 and q05), applied to
every company: see docs/stats_hypotheses.md, "Which data counts as confirmed".
"""

from __future__ import annotations

import duckdb
import pandas as pd

# One row per company-year with a GHG intensity: its confirmation status (the labels of Q3)
# and whether it is a one-year reversal. Years with a suspected scale error are left out.
GHG_STATUS_SQL = """
with latest_year as (
    select max(fiscal_year_label) as fiscal_year_label
    from fct_company_year
),

scale_error_years as (
    select distinct
        isin,
        value_fiscal_year_label as fiscal_year_label
    from fct_esg_value
    where
        is_latest_value
        and best_value_source = 'replaced_by_later_comparative'
        and metric_id in ('ghg_scope1_tco2e', 'ghg_scope2_tco2e', 'turnover_inr')
),

material_years as (
    select distinct
        isin,
        fiscal_year_label
    from fct_company_kpi_percentile
    where
        kpi_name = 'ghg_intensity_tco2e_per_cr'
        and coalesce(percentile_null_reason, '') <> 'not_material'
),

later_report as (
    select
        isin,
        value_fiscal_year_label as fiscal_year_label,
        count(distinct metric_id) filter (where classification in ('no_change', 'minor'))
            as n_inputs_confirmed,
        bool_or(classification = 'unit_inferred_from_restating_filing') as unit_inferred,
        bool_or(
            classification not in ('no_change', 'minor', 'unit_inferred_from_restating_filing')
        ) as restated_later
    from fct_restatement
    where metric_id in ('ghg_scope1_tco2e', 'ghg_scope2_tco2e')
    group by isin, value_fiscal_year_label
),

year_status as (
    select
        company_year.isin,
        company_year.sector_group,
        company_year.ranking_group,
        company_year.fiscal_year_label,
        company_year.has_comparability_break,
        company_year.ghg_intensity_tco2e_per_cr as intensity,
        material_years.isin is not null as is_ghg_material,
        case
            when company_year.fiscal_year_label = latest_year.fiscal_year_label
                then 'provisional'
            when coalesce(later_report.unit_inferred, false) then 'inferred_unit'
            when coalesce(later_report.restated_later, false) then 'restated_later'
            when coalesce(later_report.n_inputs_confirmed, 0) = 2 then 'confirmed'
            else 'not_confirmed'
        end as status
    from fct_company_year as company_year
    cross join latest_year
    left join material_years
        on
            company_year.isin = material_years.isin
            and company_year.fiscal_year_label = material_years.fiscal_year_label
    anti join scale_error_years
        on
            company_year.isin = scale_error_years.isin
            and company_year.fiscal_year_label = scale_error_years.fiscal_year_label
    left join later_report
        on
            company_year.isin = later_report.isin
            and company_year.fiscal_year_label = later_report.fiscal_year_label
    where company_year.ghg_intensity_tco2e_per_cr > 0
),

with_neighbours as (
    select
        *,
        lag(intensity) over company_years as previous_intensity,
        lead(intensity) over company_years as next_intensity
    from year_status
    window company_years as (partition by isin order by fiscal_year_label)
)

select
    isin,
    sector_group,
    ranking_group,
    fiscal_year_label,
    has_comparability_break,
    intensity,
    is_ghg_material,
    status,
    coalesce(
        previous_intensity is not null
        and next_intensity is not null
        and (
            intensity > 2 * greatest(previous_intensity, next_intensity)
            or intensity < least(previous_intensity, next_intensity) / 2
        ),
        false
    ) as is_reversal_year
from with_neighbours
order by isin, fiscal_year_label
"""

# The balanced panel of Q1 / Q5 and the plausibility screen of Q5, one row per panel company.
PANEL_SQL = """
with years as (
    select
        count(distinct fiscal_year_label) as n_years,
        min(fiscal_year_label) as first_year,
        max(fiscal_year_label) as latest_year
    from fct_company_year
),

balanced_companies as (
    select company_year.isin
    from fct_company_year as company_year
    cross join years
    group by company_year.isin, years.n_years, years.first_year
    having
        count(*) = years.n_years
        and count(company_year.ghg_intensity_tco2e_per_cr) = years.n_years
        and not bool_or(
            company_year.has_comparability_break
            and company_year.fiscal_year_label > years.first_year
        )
),

series as (
    select
        company_year.isin,
        company_year.sector_group,
        company_year.fiscal_year_label,
        company_year.turnover_cr,
        company_year.ghg_s12_tco2e,
        company_year.ghg_intensity_tco2e_per_cr,
        lag(company_year.turnover_cr) over company_years as turnover_before,
        lead(company_year.turnover_cr) over company_years as turnover_after,
        lag(company_year.ghg_s12_tco2e) over company_years as emissions_before,
        lead(company_year.ghg_s12_tco2e) over company_years as emissions_after
    from fct_company_year as company_year
    semi join balanced_companies on company_year.isin = balanced_companies.isin
    window company_years as (
        partition by company_year.isin
        order by company_year.fiscal_year_label
    )
),

per_company as (
    select
        series.isin,
        any_value(series.sector_group) as sector_group,
        max(case when series.fiscal_year_label = years.first_year then series.turnover_cr end)
            as turnover_first,
        max(case when series.fiscal_year_label = years.latest_year then series.turnover_cr end)
            as turnover_latest,
        max(case when series.fiscal_year_label = years.first_year then series.ghg_s12_tco2e end)
            as emissions_first,
        max(case when series.fiscal_year_label = years.latest_year then series.ghg_s12_tco2e end)
            as emissions_latest,
        max(
            case
                when series.fiscal_year_label = years.first_year
                    then series.ghg_intensity_tco2e_per_cr
            end
        ) as intensity_first,
        max(
            case
                when series.fiscal_year_label = years.latest_year
                    then series.ghg_intensity_tco2e_per_cr
            end
        ) as intensity_latest,
        coalesce(
            bool_or(
                series.turnover_cr > 2 * greatest(series.turnover_before, series.turnover_after)
                or series.turnover_cr < least(series.turnover_before, series.turnover_after) / 2
                or series.ghg_s12_tco2e
                > 2 * greatest(series.emissions_before, series.emissions_after)
                or series.ghg_s12_tco2e
                < least(series.emissions_before, series.emissions_after) / 2
            ) filter (
                where series.turnover_before is not null and series.turnover_after is not null
            ),
            false
        ) as has_one_year_reversal
    from series
    cross join years
    group by series.isin
)

select
    isin,
    sector_group,
    intensity_first,
    intensity_latest,
    coalesce(
        turnover_first > 0
        and emissions_first > 0
        and (
            has_one_year_reversal
            or turnover_latest / turnover_first not between 0.5 and 2
            or emissions_latest / emissions_first not between 0.5 and 2
        ),
        false
    ) as needs_review
from per_company
order by isin
"""

DQS_SQL = """
select
    disclosure_quality.isin,
    disclosure_quality.fiscal_year_label,
    disclosure_quality.sector_group,
    disclosure_quality.ranking_group,
    disclosure_quality.dqs_total,
    disclosure_quality.dqs_components_used,
    disclosure_quality.is_provisional,
    disclosure_quality.assurance_level,
    disclosure_quality.assurance_scope,
    company.ownership_type
from fct_disclosure_quality as disclosure_quality
left join dim_company as company on disclosure_quality.isin = company.isin
where disclosure_quality.dqs_total is not null
order by disclosure_quality.isin, disclosure_quality.fiscal_year_label
"""

# Material restatements with a direction, of years that have a later report.
RESTATEMENT_DIRECTION_SQL = """
select
    isin,
    value_fiscal_year_label as fiscal_year_label,
    flatters_trend
from fct_restatement
where
    classification = 'material'
    and flatters_trend is not null
    and value_fiscal_year_label < (select max(fiscal_year_label) from fct_company_year)
order by isin, value_fiscal_year_label, metric_id, dimension_key
"""

# Per company-year: how many metrics the next report could be compared on, and how many of
# those it restated materially.
RESTATEMENT_BY_COMPANY_YEAR_SQL = """
select
    isin,
    value_fiscal_year_label as fiscal_year_label,
    count(*) filter (where is_compared) as n_compared,
    count(*) filter (where is_compared and classification = 'material') as n_material
from fct_restatement
where value_fiscal_year_label < (select max(fiscal_year_label) from fct_company_year)
group by isin, value_fiscal_year_label
having count(*) filter (where is_compared) > 0
order by isin, value_fiscal_year_label
"""


def _frame(con: duckdb.DuckDBPyConnection, sql: str) -> pd.DataFrame:
    return con.sql(sql).df()


def ghg_status(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Company-years with a GHG intensity; `is_confirmed` follows the Week 10 rules."""
    frame = _frame(con, GHG_STATUS_SQL)
    frame["is_confirmed"] = (frame["status"] == "confirmed") & ~frame["is_reversal_year"].astype(
        bool
    )
    return frame


def panel(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """The balanced panel (one row per company) with the `needs_review` screen of Q5."""
    return _frame(con, PANEL_SQL)


def disclosure_quality(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return _frame(con, DQS_SQL)


def restatement_directions(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return _frame(con, RESTATEMENT_DIRECTION_SQL)


def restatements_by_company_year(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return _frame(con, RESTATEMENT_BY_COMPANY_YEAR_SQL)


def years(con: duckdb.DuckDBPyConnection) -> list[str]:
    """All financial years in the warehouse, oldest first."""
    rows = con.sql(
        "select distinct fiscal_year_label from fct_company_year order by fiscal_year_label"
    ).fetchall()
    return [row[0] for row in rows]
