-- Q3. Leaders and laggards: who moved most on GHG intensity in one year?
--
-- Business question  Within each ranking group, which company had the largest year-on-year
--                    improvement in GHG intensity, and which the largest deterioration - and how
--                    far can each of those moves be trusted?
-- Stakeholder        Portfolio manager comparing a company with its real peers.
-- Method             Year-on-year change of the computed intensity (Scope 1+2 per Rs crore) for
--                    consecutive years of the same company, only in ranking groups where GHG
--                    intensity is material (so not Financials). Left out altogether: years with
--                    a comparability break and years in which an emissions or turnover figure
--                    was a suspected scale error. Every remaining pair gets a CONFIDENCE:
--                      confirmed          for both years the next report repeats Scope 1 and
--                                         Scope 2 unchanged (or within 5%), and no unit was
--                                         inferred
--                      provisional        the pair ends in the latest year: no later report
--                                         exists yet to confirm it
--                      inferred_unit      a year whose emissions unit was not filed and was
--                                         taken from the next report (FY2022-23 filings)
--                      restated_later     the next report changed Scope 1 or Scope 2 materially
--                      one_year_reversal  one end of the pair is a year more than twice, or less
--                                         than half of, BOTH its neighbours: a value that jumps
--                                         and comes straight back is a filing slip
--                      not_confirmed      nothing in a later report to check against
--                    Only CONFIRMED pairs are ranked (and published). The others are kept in
--                    the result with their label, so nothing disappears silently.
-- SQL techniques     LAG and LEAD over a named WINDOW, semi join and anti join, conditional
--                    aggregation with BOOL_OR, CASE with a priority order, RANK and ROW_NUMBER
--                    inside CASE (a conditional rank), COUNT OVER for the group-size rule.
-- Caveats            "Confirmed" means the company repeated the figure a year later, not that
--                    the figure is right: a mistake filed twice stays (the reversal screen
--                    catches the ones that are corrected in the following year). Turnover has no
--                    comparative in the filings and cannot be confirmed this way. The reversal
--                    screen is a rule of this analysis, not of the warehouse, and cannot test a
--                    company's first or latest year. A ranking needs at least 5 comparable
--                    companies in the group that year.

-- result: yoy_changes_with_confidence
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

-- company-years in a ranking group where GHG intensity is ranked at all
material_years as (
    select
        isin,
        fiscal_year_label
    from fct_company_kpi_percentile
    where
        kpi_name = 'ghg_intensity_tco2e_per_cr'
        and coalesce(percentile_null_reason, '') <> 'not_material'
),

-- what the next report says about the Scope 1 and Scope 2 figures of each company-year
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
        company_year.display_name,
        company_year.ranking_group,
        company_year.fiscal_year_label,
        company_year.has_comparability_break,
        company_year.ghg_intensity_tco2e_per_cr as intensity,
        cast(substr(company_year.fiscal_year_label, 3, 4) as integer) as year_start,
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
    semi join material_years
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
        lag(fiscal_year_label) over company_years as previous_fiscal_year_label,
        lag(year_start) over company_years as previous_year_start,
        lag(intensity) over company_years as previous_intensity,
        lag(status) over company_years as previous_status,
        lead(intensity) over company_years as next_intensity
    from year_status
    window company_years as (partition by isin order by fiscal_year_label)
),

flagged as (
    select
        *,
        -- needs both neighbours: the first and the latest year of a company cannot be tested
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
),

year_pairs as (
    select
        *,
        coalesce(
            lag(is_reversal_year) over (partition by isin order by fiscal_year_label), false
        ) as previous_is_reversal_year
    from flagged
),

changes as (
    select
        ranking_group,
        display_name,
        previous_fiscal_year_label,
        fiscal_year_label,
        previous_intensity,
        intensity,
        100 * (intensity / previous_intensity - 1) as change_pct,
        -- the weakest link decides
        case
            when is_reversal_year or previous_is_reversal_year then 'one_year_reversal'
            when 'provisional' in (status, previous_status) then 'provisional'
            when 'inferred_unit' in (status, previous_status) then 'inferred_unit'
            when 'restated_later' in (status, previous_status) then 'restated_later'
            when status = 'confirmed' and previous_status = 'confirmed' then 'confirmed'
            else 'not_confirmed'
        end as confidence,
        count(*) over (partition by ranking_group, fiscal_year_label) as n_companies_compared
    from year_pairs
    where
        previous_year_start = year_start - 1  -- consecutive years only
        and not has_comparability_break       -- the later year must be like for like
),

rankable as (
    select
        *,
        confidence = 'confirmed' and n_companies_compared >= 5 as is_ranked
    from changes
)

select
    ranking_group,
    display_name,
    previous_fiscal_year_label as from_year,
    fiscal_year_label as to_year,
    round(previous_intensity, 2) as intensity_from,
    round(intensity, 2) as intensity_to,
    round(change_pct, 1) as change_pct,
    confidence,
    n_companies_compared,
    is_ranked,
    -- 1 = largest improvement (most negative change) among the ranked pairs
    case
        when is_ranked
            then rank() over (partition by ranking_group, is_ranked order by change_pct asc)
    end as improvement_rank_in_group,
    case
        when is_ranked
            then rank() over (partition by ranking_group, is_ranked order by change_pct desc)
    end as deterioration_rank_in_group,
    case
        when is_ranked then row_number() over (partition by is_ranked order by change_pct asc)
    end as improvement_rank_overall,
    case
        when is_ranked then row_number() over (partition by is_ranked order by change_pct desc)
    end as deterioration_rank_overall
from rankable
order by is_ranked desc, ranking_group asc, change_pct asc;

-- result: one_year_reversals_set_aside
-- The company-years the screen sets aside (all ranking groups, material or not): a value more
-- than twice, or less than half of, both the year before and the year after.
with with_neighbours as (
    select
        display_name,
        ranking_group,
        fiscal_year_label,
        ghg_intensity_tco2e_per_cr as intensity,
        lag(ghg_intensity_tco2e_per_cr) over company_years as previous_intensity,
        lead(ghg_intensity_tco2e_per_cr) over company_years as next_intensity
    from fct_company_year
    where ghg_intensity_tco2e_per_cr > 0
    window company_years as (partition by isin order by fiscal_year_label)
)

select
    ranking_group,
    display_name,
    fiscal_year_label,
    round(previous_intensity, 2) as intensity_year_before,
    round(intensity, 2) as intensity,
    round(next_intensity, 2) as intensity_year_after,
    case
        when intensity > 2 * greatest(previous_intensity, next_intensity)
            then 'more than twice both neighbours'
        else 'less than half of both neighbours'
    end as pattern
from with_neighbours
where
    previous_intensity is not null
    and next_intensity is not null
    and (
        intensity > 2 * greatest(previous_intensity, next_intensity)
        or intensity < least(previous_intensity, next_intensity) / 2
    )
order by ranking_group, display_name, fiscal_year_label;
