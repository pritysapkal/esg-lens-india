-- Q8. Disclosure quality: where is reporting strongest, and who improved most?
--
-- Business question  What is the typical Disclosure Quality Score (DQS) by sector group and by
--                    ownership type, and which companies improved their score most between the
--                    two years that can be compared?
-- Stakeholder        Data user deciding how far to trust a group's ESG numbers; a company
--                    secretary benchmarking the report against peers.
-- Method             Median DQS (typical company) for every combination of sector group and
--                    ownership type, with subtotals per sector group, per ownership type and a
--                    grand total - always within one financial year, because scores of different
--                    years are built from different parts. Improvers: change in DQS between
--                    consecutive years in which all four components were scored (today
--                    FY2023-24 to FY2024-25), so the two scores are built the same way.
-- SQL techniques     GROUP BY GROUPING SETS with GROUPING() to label the subtotal rows, MEDIAN,
--                    CASE for the group-size rule, LAG over a named WINDOW, QUALIFY with
--                    ROW_NUMBER for a top-10.
-- Caveats            DQS measures machine-readable (XBRL) disclosure quality, not ESG
--                    performance, and is not an ESG rating. Scores sit in a narrow band (half of
--                    them between 80 and 90), so small differences between groups mean little.
--                    The latest year is provisional. A median is shown only for 5 companies or
--                    more: most sector x ownership cells are too small and show the count only.

-- result: dqs_median_by_sector_and_ownership
with scores as (
    select
        disclosure_quality.fiscal_year_label,
        disclosure_quality.sector_group,
        company_year.ownership_type,
        disclosure_quality.isin,
        disclosure_quality.dqs_total
    from fct_disclosure_quality as disclosure_quality
    inner join fct_company_year as company_year
        on
            disclosure_quality.isin = company_year.isin
            and disclosure_quality.fiscal_year_label = company_year.fiscal_year_label
    where disclosure_quality.dqs_total is not null
),

grouped as (
    select
        fiscal_year_label,
        sector_group,
        ownership_type,
        -- 0 = both given, 1 = ownership subtotalled, 2 = sector subtotalled, 3 = grand total
        grouping(sector_group, ownership_type) as subtotal_code,
        count(distinct isin) as n_companies,
        median(dqs_total) as dqs_median
    from scores
    group by grouping sets (  -- noqa: PRS
        (fiscal_year_label, sector_group, ownership_type),
        (fiscal_year_label, sector_group),
        (fiscal_year_label, ownership_type),
        (fiscal_year_label)
    )
)

select
    fiscal_year_label,
    case subtotal_code
        when 0 then 'sector group x ownership type'
        when 1 then 'sector group'
        when 2 then 'ownership type'
        else 'all companies'
    end as subtotal_level,
    coalesce(sector_group, 'All sector groups') as sector_group,
    coalesce(ownership_type, 'All ownership types') as ownership_type,
    n_companies,
    case when n_companies >= 5 then round(dqs_median, 1) end as dqs_median,
    case when n_companies < 5 then 'fewer_than_5_companies' end as suppressed_reason,
    -- unrounded, for the reconciliation with the semantic layer (tests/test_analysis.py)
    case when n_companies >= 5 then dqs_median end as dqs_median_exact
from grouped
order by fiscal_year_label asc, subtotal_code desc, sector_group asc, ownership_type asc;

-- result: biggest_dqs_improvers
with scored as (
    select
        isin,
        display_name,
        ranking_group,
        fiscal_year_label,
        dqs_total,
        dqs_grade,
        dqs_components_used,
        cast(substr(fiscal_year_label, 3, 4) as integer) as year_start
    from fct_disclosure_quality
    where dqs_total is not null
),

year_on_year as (
    select
        display_name,
        ranking_group,
        fiscal_year_label,
        dqs_total,
        dqs_grade,
        dqs_components_used,
        year_start,
        lag(fiscal_year_label) over company_years as previous_fiscal_year_label,
        lag(year_start) over company_years as previous_year_start,
        lag(dqs_total) over company_years as previous_dqs_total,
        lag(dqs_grade) over company_years as previous_dqs_grade,
        lag(dqs_components_used) over company_years as previous_components_used
    from scored
    window company_years as (partition by isin order by fiscal_year_label)
)

select
    display_name,
    ranking_group,
    previous_fiscal_year_label as from_year,
    fiscal_year_label as to_year,
    previous_dqs_total as dqs_from,
    dqs_total as dqs_to,
    round(dqs_total - previous_dqs_total, 1) as dqs_change_points,
    previous_dqs_grade as grade_from,
    dqs_grade as grade_to
from year_on_year
where
    previous_year_start = year_start - 1
    -- both scores built from all four components, so they are comparable
    and dqs_components_used = 4
    and previous_components_used = 4
qualify
    row_number() over (order by dqs_total - previous_dqs_total desc, display_name asc) <= 10
order by dqs_change_points desc, display_name asc;
