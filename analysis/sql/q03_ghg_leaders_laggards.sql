-- Q3. Leaders and laggards: who moved most on GHG intensity in one year?
--
-- Business question  Within each ranking group, which company had the largest year-on-year
--                    improvement in GHG intensity, and which the largest deterioration?
-- Stakeholder        Portfolio manager comparing a company with its real peers.
-- Method             Year-on-year change of the computed intensity (Scope 1+2 per Rs crore) for
--                    consecutive years of the same company, only in ranking groups where GHG
--                    intensity is material (so not Financials). Left out:
--                      * years with a comparability break (merger, demerger, boundary change);
--                      * years in which an emissions or turnover figure was a suspected scale
--                        error (replaced by the figure of the later report);
--                      * one-year spikes: a year more than 3 times above, or below a third of,
--                        BOTH its neighbours. A value that jumps and comes straight back is a
--                        reporting slip, not a change in the business. These are listed in the
--                        second result so that nothing disappears silently.
--                    Ranked inside the ranking group over all year pairs; a year pair counts
--                    only when at least 5 companies of the group can be compared in it.
-- SQL techniques     LAG and LEAD over a named WINDOW, anti join and semi join, RANK, QUALIFY,
--                    COUNT OVER for the group-size rule.
-- Caveats            The spike screen is a rule of this analysis, not of the warehouse, and it
--                    cannot test the first or the latest year (one neighbour is missing). A big
--                    one-year move is a reason to read the report, not a verdict: turnover
--                    swings move intensity without any change in emissions.

-- result: largest_moves_by_ranking_group
with scale_error_years as (
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

clean_years as (
    select
        company_year.isin,
        company_year.display_name,
        company_year.ranking_group,
        company_year.fiscal_year_label,
        company_year.has_comparability_break,
        company_year.ghg_intensity_tco2e_per_cr as intensity,
        cast(substr(company_year.fiscal_year_label, 3, 4) as integer) as year_start
    from fct_company_year as company_year
    semi join material_years
        on
            company_year.isin = material_years.isin
            and company_year.fiscal_year_label = material_years.fiscal_year_label
    anti join scale_error_years
        on
            company_year.isin = scale_error_years.isin
            and company_year.fiscal_year_label = scale_error_years.fiscal_year_label
    where company_year.ghg_intensity_tco2e_per_cr > 0
),

with_neighbours as (
    select
        isin,
        display_name,
        ranking_group,
        fiscal_year_label,
        has_comparability_break,
        intensity,
        year_start,
        lag(fiscal_year_label) over company_years as previous_fiscal_year_label,
        lag(year_start) over company_years as previous_year_start,
        lag(intensity) over company_years as previous_intensity,
        lead(intensity) over company_years as next_intensity
    from clean_years
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
                intensity > 3 * greatest(previous_intensity, next_intensity)
                or intensity < least(previous_intensity, next_intensity) / 3
            ),
            false
        ) as is_one_year_spike
    from with_neighbours
),

year_pairs as (
    select
        *,
        coalesce(
            lag(is_one_year_spike) over (partition by isin order by fiscal_year_label), false
        ) as previous_is_one_year_spike
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
        count(*) over (partition by ranking_group, fiscal_year_label) as n_companies_compared
    from year_pairs
    where
        previous_year_start = year_start - 1  -- consecutive years only
        and not has_comparability_break       -- the later year must be like for like
        and not is_one_year_spike             -- neither end of the pair is a spike year
        and not previous_is_one_year_spike
)

select
    ranking_group,
    case when change_pct < 0 then 'largest improvement' else 'largest deterioration' end
        as move_type,
    display_name,
    previous_fiscal_year_label as from_year,
    fiscal_year_label as to_year,
    round(previous_intensity, 2) as intensity_from,
    round(intensity, 2) as intensity_to,
    round(change_pct, 1) as change_pct,
    n_companies_compared
from changes
where n_companies_compared >= 5
qualify
    rank() over (partition by ranking_group order by change_pct asc) = 1
    or rank() over (partition by ranking_group order by change_pct desc) = 1
order by ranking_group, change_pct;

-- result: one_year_spikes_set_aside
-- The company-years the screen sets aside (all ranking groups, material or not): a value more
-- than 3 times above, or below a third of, both the year before and the year after.
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
    round(intensity / greatest(previous_intensity, next_intensity), 1)
        as times_the_higher_neighbour
from with_neighbours
where
    previous_intensity is not null
    and next_intensity is not null
    and (
        intensity > 3 * greatest(previous_intensity, next_intensity)
        or intensity < least(previous_intensity, next_intensity) / 3
    )
order by times_the_higher_neighbour desc;
