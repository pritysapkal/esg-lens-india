-- Every flagged, inferred or corrected value in one place, for review.
--   value_flag        a metric value with a normalisation_flag (one row per flag)
--   turnover_scale    a turnover read as crore / million / lakh, or a plausible-looking turnover
--                     that is far from the company's other years (confidence not high)
--   mtco2e_check      a MtCO2e filing whose intensity is > 100x off company or peers
--   manual_override   an approved correction from seeds/manual_overrides.csv (one row per
--                     overridden value); counts against the Disclosure Quality Score later

with flagged_values as (
    select
        'value_flag' as exception_type,
        flag.flag as exception_code,
        values_normalised.symbol,
        values_normalised.fiscal_year_label,
        values_normalised.filing_id,
        values_normalised.metric_id,
        values_normalised.fact_id,
        values_normalised.period_role,
        values_normalised.raw_value,
        values_normalised.value_std,
        coalesce(
            values_normalised.correction_reason,
            'unit ' || coalesce(values_normalised.unit_label_effective, '') || ' -> '
            || coalesce(values_normalised.unit_std, '')
        ) as detail,
        null as confidence
    from {{ ref('int_values_normalised') }} as values_normalised
    cross join unnest(string_split(values_normalised.normalisation_flag, '|')) as flag (flag)
    where
        values_normalised.normalisation_flag != ''
        and flag.flag != 'manual_override'
),

overrides as (
    select
        'manual_override' as exception_type,
        values_normalised.override_id as exception_code,
        values_normalised.symbol,
        values_normalised.fiscal_year_label,
        values_normalised.filing_id,
        values_normalised.metric_id,
        values_normalised.fact_id,
        values_normalised.period_role,
        values_normalised.raw_value,
        values_normalised.value_std,
        values_normalised.correction_reason || '; automatic value '
        || values_normalised.value_std_auto as detail,
        'approved' as confidence
    from {{ ref('int_values_normalised') }} as values_normalised
    where values_normalised.override_id is not null
),

turnover as (
    select
        'turnover_scale' as exception_type,
        case when scale_applied then 'scale_' || scale_name else 'inconsistent_years' end
            as exception_code,
        symbol,
        fiscal_year_label,
        filing_id,
        'turnover_inr' as metric_id,
        null as fact_id,
        'CY' as period_role,
        cast(turnover_raw as varchar) as raw_value,
        turnover_inr as value_std,
        coalesce(
            correction_reason,
            'not corrected; ' || round(ratio_to_other_years, 2) || 'x the other years'
        ) as detail,
        confidence
    from {{ ref('int_turnover_corrected') }}
    where scale_applied or confidence != 'high'
),

mtco2e as (
    select
        'mtco2e_check' as exception_type,
        case
            when likely_megatonnes then 'likely_megatonnes'
            else 'implausible_intensity'
        end as exception_code,
        symbol,
        fiscal_year_label,
        filing_id,
        'ghg_scope1_tco2e' as metric_id,
        null as fact_id,
        'CY' as period_role,
        null as raw_value,
        intensity_tco2e_per_inr_cr as value_std,
        'Scope 1+2 intensity ' || round(intensity_tco2e_per_inr_cr, 2)
        || ' tCO2e/INR cr; company other years '
        || coalesce(round(company_other_years_median, 2), 0)
        || ', industry peers ' || coalesce(round(industry_peer_median, 2), 0) as detail,
        null as confidence
    from {{ ref('int_mtco2e_check') }}
    where is_implausible
)

select * from flagged_values
union all
select * from overrides
union all
select * from turnover
union all
select * from mtco2e
