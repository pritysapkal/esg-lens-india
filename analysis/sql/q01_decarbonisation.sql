-- Q1. Decarbonisation: is each sector group getting less carbon-heavy?
--
-- Business question  How did GHG intensity (Scope 1+2 per Rs crore of turnover) move from the
--                    first to the latest financial year in each sector group?
-- Stakeholder        Investor or lender who wants to know whether a sector is really improving.
-- Method             Two honest group figures, never an average of company ratios:
--                      whole group     = sum of emissions / sum of turnover (ratio of sums)
--                      typical company = median of the company intensities
--                    Each on two sets of companies:
--                      all companies  = everyone who filed that year (the set changes over time)
--                      balanced panel = only companies with an intensity in every year and no
--                                       comparability break (merger, demerger, boundary change)
--                                       after the first year
--                    The gap between the two sets is the composition effect: movement that comes
--                    from companies entering, leaving or restructuring, not from decarbonising.
-- SQL techniques     CTEs, HAVING on per-company counts, semi join, ratio of sums, MEDIAN, named
--                    WINDOW with FIRST_VALUE, conditional pivot (MAX CASE), UNION ALL.
-- Caveats            Turnover is the only denominator, so a price rise alone lowers intensity.
--                    FY2022-23 units were partly inferred. Sector groups are broad: Asset-heavy
--                    mixes power, steel, cement and cars. The balanced panel is the cleaner
--                    trend but a smaller world: see who it leaves out in the third result.
--                    A group figure is shown only for 5 companies or more.

-- result: ghg_intensity_by_sector
with years as (
    select
        count(distinct fiscal_year_label) as n_years,
        min(fiscal_year_label) as first_year
    from fct_company_year
),

-- companies that can be followed like for like through every year
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

-- only company-years with an intensity, so that sums and counts cover the same companies
with_intensity as (
    select
        isin,
        sector_group,
        fiscal_year_label,
        ghg_s12_tco2e,
        turnover_cr,
        ghg_intensity_tco2e_per_cr
    from fct_company_year
    where ghg_intensity_tco2e_per_cr is not null
),

panels as (
    select
        'all companies' as panel,
        with_intensity.*
    from with_intensity
    union all
    select
        'balanced panel' as panel,
        with_intensity.*
    from with_intensity
    semi join balanced_companies on with_intensity.isin = balanced_companies.isin
),

by_group as (
    select
        panel,
        sector_group,
        fiscal_year_label,
        count(distinct isin) as n_companies,
        sum(ghg_s12_tco2e) / sum(turnover_cr) as ghg_intensity_agg,
        median(ghg_intensity_tco2e_per_cr) as ghg_intensity_median
    from panels
    group by panel, sector_group, fiscal_year_label
),

-- a group figure needs at least 5 companies
reliable as (
    select
        panel,
        sector_group,
        fiscal_year_label,
        n_companies,
        case when n_companies >= 5 then ghg_intensity_agg end as ghg_intensity_agg,
        case when n_companies >= 5 then ghg_intensity_median end as ghg_intensity_median
    from by_group
)

select
    panel,
    sector_group,
    fiscal_year_label,
    n_companies,
    round(ghg_intensity_agg, 2) as ghg_intensity_agg,
    round(ghg_intensity_median, 2) as ghg_intensity_median,
    round(100 * (ghg_intensity_agg / first_value(ghg_intensity_agg) over since_first - 1), 1)
        as agg_change_vs_first_year_pct,
    round(
        100 * (ghg_intensity_median / first_value(ghg_intensity_median) over since_first - 1), 1
    ) as median_change_vs_first_year_pct,
    -- unrounded, for the reconciliation with the semantic layer (tests/test_analysis.py)
    ghg_intensity_agg as ghg_intensity_agg_exact,
    ghg_intensity_median as ghg_intensity_median_exact
from reliable
window since_first as (partition by panel, sector_group order by fiscal_year_label)
order by sector_group, panel, fiscal_year_label;

-- result: composition_effect
-- First to latest year, both panels side by side. The difference is what entry, exit and
-- restructuring of companies add to (or hide from) the headline trend.
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

with_intensity as (
    select
        isin,
        sector_group,
        fiscal_year_label,
        ghg_s12_tco2e,
        turnover_cr
    from fct_company_year
    where ghg_intensity_tco2e_per_cr is not null
),

panels as (
    select
        'all' as panel,
        with_intensity.*
    from with_intensity
    union all
    select
        'balanced' as panel,
        with_intensity.*
    from with_intensity
    semi join balanced_companies on with_intensity.isin = balanced_companies.isin
),

endpoints as (
    select
        panels.panel,
        panels.sector_group,
        panels.fiscal_year_label = years.latest_year as is_latest_year,
        count(distinct panels.isin) as n_companies,
        sum(panels.ghg_s12_tco2e) / sum(panels.turnover_cr) as ghg_intensity_agg
    from panels
    cross join years
    where panels.fiscal_year_label in (years.first_year, years.latest_year)
    group by panels.panel, panels.sector_group, is_latest_year
),

-- one row per sector group: both panels, first and latest year, as columns
side_by_side as (
    select
        sector_group,
        max(case when panel = 'all' and is_latest_year then n_companies end) as n_all,
        max(case when panel = 'balanced' and is_latest_year then n_companies end) as n_balanced,
        max(case when panel = 'all' and not is_latest_year then ghg_intensity_agg end)
            as all_first,
        max(case when panel = 'all' and is_latest_year then ghg_intensity_agg end)
            as all_latest,
        max(case when panel = 'balanced' and not is_latest_year then ghg_intensity_agg end)
            as balanced_first,
        max(case when panel = 'balanced' and is_latest_year then ghg_intensity_agg end)
            as balanced_latest
    from endpoints
    group by sector_group
),

changes as (
    select
        sector_group,
        n_all,
        coalesce(n_balanced, 0) as n_balanced,
        100 * (all_latest / all_first - 1) as all_change_pct,
        100 * (balanced_latest / balanced_first - 1) as balanced_change_pct
    from side_by_side
)

select
    sector_group,
    n_all as n_companies_all_latest_year,
    n_balanced as n_companies_balanced,
    round(all_change_pct, 1) as all_companies_change_pct,
    case when n_balanced >= 5 then round(balanced_change_pct, 1) end
        as balanced_panel_change_pct,
    case when n_balanced >= 5 then round(all_change_pct - balanced_change_pct, 1) end
        as composition_effect_pp
from changes
order by sector_group;

-- result: outside_the_balanced_panel
-- Who the balanced panel leaves out, and why. If the companies left out are the big emitters,
-- the balanced panel describes a different (smaller) world than the headline figure.
with years as (
    select
        count(distinct fiscal_year_label) as n_years,
        min(fiscal_year_label) as first_year
    from fct_company_year
),

per_company as (
    select
        company_year.isin,
        any_value(company_year.display_name) as display_name,
        any_value(company_year.sector_group) as sector_group,
        count(*) as n_years_filed,
        count(company_year.ghg_intensity_tco2e_per_cr) as n_years_with_intensity,
        bool_or(
            company_year.has_comparability_break
            and company_year.fiscal_year_label > years.first_year
        ) as has_break,
        string_agg(
            distinct company_year.comparability_break_reason, ' + '
            order by company_year.comparability_break_reason
        ) filter (where company_year.fiscal_year_label > years.first_year) as break_reason,
        years.n_years
    from fct_company_year as company_year
    cross join years
    group by company_year.isin, years.n_years, years.first_year
)

select
    sector_group,
    display_name,
    n_years_filed,
    case
        when n_years_filed < n_years then 'not filed in every year'
        when n_years_with_intensity < n_years then 'no intensity in some year'
        else 'comparability break: ' || coalesce(break_reason, 'unspecified')
    end as reason_left_out
from per_company
where n_years_filed < n_years or n_years_with_intensity < n_years or has_break
order by sector_group, display_name;
