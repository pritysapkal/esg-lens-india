-- Q10. Disclosure quality and carbon performance: do they go together?
--
-- Business question  Inside each ranking group, are the companies with better disclosure
--                    quality also the ones with better (lower) GHG intensity?
-- Stakeholder        ESG analyst who wants to know whether a well-made report is a sign of a
--                    well-run footprint - or only of a well-run reporting team.
-- Method             Latest year in which the Disclosure Quality Score is final (all four
--                    components, not provisional). Each company is placed in one of four
--                    quadrants: DQS above or below the median of its ranking group, crossed with
--                    GHG-intensity percentile in the better or the worse half of the group
--                    (percentile from fct_company_kpi_percentile, 100 = lowest intensity). Only
--                    ranking groups where GHG intensity is ranked: 5 companies or more and the
--                    metric material, so not Financials.
-- SQL techniques     Scalar subquery for the year, MEDIAN as a window function, CASE quadrants,
--                    cross-tabulation with COUNT FILTER, share of total with SUM OVER, UNION ALL
--                    total row.
-- Caveats            DESCRIPTIVE ONLY. The most this split can say is whether an association
--                    is visible in it or not; it cannot show that there is none, and it says
--                    nothing about cause. With 34 companies a few of them changing side would
--                    change the picture. The relationship is tested formally in Week 11. A company
--                    exactly on the group median counts as "at or above".

-- result: quadrants_overall
with final_year as (
    select max(fiscal_year_label) as fiscal_year_label
    from fct_disclosure_quality
    where dqs_components_used = 4 and not is_provisional
),

placed as (
    select
        disclosure_quality.ranking_group,
        disclosure_quality.isin,
        disclosure_quality.dqs_total
        >= median(disclosure_quality.dqs_total) over (
            partition by disclosure_quality.ranking_group
        ) as dqs_at_or_above_median,
        percentile.percentile_in_group >= 50 as ghg_in_better_half
    from fct_disclosure_quality as disclosure_quality
    inner join final_year
        on disclosure_quality.fiscal_year_label = final_year.fiscal_year_label
    inner join fct_company_kpi_percentile as percentile
        on
            disclosure_quality.isin = percentile.isin
            and disclosure_quality.fiscal_year_label = percentile.fiscal_year_label
            and percentile.kpi_name = 'ghg_intensity_tco2e_per_cr'
    where
        disclosure_quality.dqs_total is not null
        and percentile.percentile_in_group is not null
),

quadrants as (
    select
        case when dqs_at_or_above_median then 'DQS at or above median' else 'DQS below median' end
            as disclosure_quality_half,
        case when ghg_in_better_half then 'lower GHG intensity' else 'higher GHG intensity' end
            as ghg_half
    from placed
)

select
    disclosure_quality_half,
    ghg_half,
    count(*) as n_companies,
    round(100.0 * count(*) / sum(count(*)) over (), 1) as share_of_all_pct,
    round(100.0 * count(*) / sum(count(*)) over (partition by disclosure_quality_half), 1)
        as share_within_disclosure_half_pct
from quadrants
group by disclosure_quality_half, ghg_half
order by disclosure_quality_half, ghg_half;

-- result: quadrants_by_ranking_group
with final_year as (
    select max(fiscal_year_label) as fiscal_year_label
    from fct_disclosure_quality
    where dqs_components_used = 4 and not is_provisional
),

placed as (
    select
        disclosure_quality.fiscal_year_label,
        disclosure_quality.ranking_group,
        disclosure_quality.dqs_total
        >= median(disclosure_quality.dqs_total) over (
            partition by disclosure_quality.ranking_group
        ) as dqs_at_or_above_median,
        percentile.percentile_in_group >= 50 as ghg_in_better_half
    from fct_disclosure_quality as disclosure_quality
    inner join final_year
        on disclosure_quality.fiscal_year_label = final_year.fiscal_year_label
    inner join fct_company_kpi_percentile as percentile
        on
            disclosure_quality.isin = percentile.isin
            and disclosure_quality.fiscal_year_label = percentile.fiscal_year_label
            and percentile.kpi_name = 'ghg_intensity_tco2e_per_cr'
    where
        disclosure_quality.dqs_total is not null
        and percentile.percentile_in_group is not null
),

with_total as (
    select
        fiscal_year_label,
        ranking_group,
        dqs_at_or_above_median,
        ghg_in_better_half
    from placed
    union all
    select
        fiscal_year_label,
        'All ranked groups' as ranking_group,
        dqs_at_or_above_median,
        ghg_in_better_half
    from placed
)

select
    fiscal_year_label,
    ranking_group,
    count(*) as n_companies,
    count(*) filter (where dqs_at_or_above_median and ghg_in_better_half)
        as good_disclosure_lower_ghg,
    count(*) filter (where dqs_at_or_above_median and not ghg_in_better_half)
        as good_disclosure_higher_ghg,
    count(*) filter (where not dqs_at_or_above_median and ghg_in_better_half)
        as weak_disclosure_lower_ghg,
    count(*) filter (where not dqs_at_or_above_median and not ghg_in_better_half)
        as weak_disclosure_higher_ghg,
    -- companies on the diagonal: both better or both worse
    round(
        100.0 * count(*) filter (where dqs_at_or_above_median = ghg_in_better_half) / count(*), 1
    ) as same_side_share_pct
from with_total
group by fiscal_year_label, ranking_group
order by ranking_group;
