-- PUBLIC year-on-year change of GHG intensity (Scope 1+2 per Rs crore, computed by us) for
-- consecutive years of a company, with a CONFIDENCE label, from the Week 10 analysis
-- (analysis/sql/q03_ghg_leaders_laggards.sql, result yoy_changes_with_confidence; the same SQL
-- with ref()). Only confirmed pairs in a group of 5 or more comparable companies are ranked.
-- Intensities and changes are values we calculate; no filed quantity is a column.
-- tests/test_app.py checks that this model equals the Week 10 result row by row.

with latest_year as (
    select max(fiscal_year_label) as fiscal_year_label
    from {{ ref('fct_company_year') }}
),

scale_error_years as (
    select distinct
        isin,
        value_fiscal_year_label as fiscal_year_label
    from {{ ref('fct_esg_value') }}
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
    from {{ ref('fct_company_kpi_percentile') }}
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
    from {{ ref('fct_restatement') }}
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
    from {{ ref('fct_company_year') }} as company_year
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
        isin,
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
    isin,
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
order by is_ranked desc, ranking_group asc, change_pct asc
