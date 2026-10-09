-- Mapped facts with values converted to the metric's standard unit (unit_std).
--   value_std = value x multiplier (seeds/unit_normalisation.csv, keyed on unit label + unit_std)
--   percent:  decimals 0-1 are x100 into value_pct; values > 1 are taken as already in percent
--             (not double-scaled) and flagged pct_given_as_0_100
--   duration: ISO 8601 'P59D' -> 59 days
--   turnover: corrected scale from int_turnover_corrected
--   old-taxonomy 'pure' quantities: unit from int_implied_units
-- raw_value and value_num are kept; every changed or inferred value has a normalisation_flag,
-- and corrections a correction_reason. NA text / zero stay distinct; missing = no row.

{{ config(materialized='table') }}

with facts as (
    select * from {{ ref('int_period_role') }}
),

metric_map as (
    select * from {{ ref('concept_metric_map') }}
),

units as (
    select * from {{ ref('unit_normalisation') }}
),

implied as (
    select * from {{ ref('int_implied_units') }}
),

turnover as (
    select * from {{ ref('int_turnover_corrected') }}
),

mapped as (
    select
        facts.*,
        metric_map.metric_id,
        metric_map.role,
        metric_map.unit_std,
        metric_map.value_kind,
        metric_map.allowed_dimension_axes
    from facts
    inner join metric_map
        on
            facts.taxonomy_version = metric_map.taxonomy_version
            and facts.concept = metric_map.concept
),

resolved as (
    select
        mapped.*,
        implied.unit_source as implied_unit_source,
        implied.unit_conflict,
        coalesce(implied.implied_unit_label, mapped.unit_label, '(none)') as unit_label_effective,
        case
            when mapped.value_kind = 'numeric' then mapped.value_num
            when mapped.value_kind = 'text' and mapped.unit_std is not null
                then {{ number_from_text('mapped.value_text') }}
        end as value_in
    from mapped
    left join implied
        on
            mapped.filing_id = implied.filing_id
            and mapped.metric_id = implied.metric_id
            and not mapped.has_dimensions
            and coalesce(mapped.unit_label, 'pure') = 'pure'
),

converted as (
    select
        resolved.*,
        units.multiplier,
        turnover.turnover_inr,
        turnover.scale_applied as turnover_scale_applied,
        turnover.correction_reason as turnover_correction_reason,
        case
            when
                resolved.value_kind = 'duration'
                then {{ iso_duration_days('resolved.value_text') }}
            when resolved.unit_std = 'pct' and resolved.value_in > 1 then resolved.value_in
            when resolved.metric_id = 'turnover_inr' and turnover.turnover_inr is not null
                then turnover.turnover_inr
            else {{ round_sig("resolved.value_in * units.multiplier") }}
        end as value_std
    from resolved
    left join units
        on
            resolved.unit_label_effective = units.unit_label_raw
            and resolved.unit_std = units.unit_std
    left join turnover
        on
            resolved.filing_id = turnover.filing_id
            and resolved.metric_id = 'turnover_inr'
            and resolved.period_role = 'CY'
            and not resolved.has_dimensions
)

select
    fact_id,
    filing_id,
    symbol,
    isin,
    fiscal_year_label,
    taxonomy_version,
    filing_period_start,
    filing_period_end,
    is_non_standard_period,
    concept,
    metric_id,
    role,
    value_kind,
    allowed_dimension_axes,
    context_ref,
    period_type,
    start_date,
    end_date,
    instant_date,
    period_role,
    value_period_end,
    value_fiscal_year_label,
    dimension_key,
    has_dimensions,
    raw_value,
    value_num,
    value_text,
    unit_label,
    unit_label_effective,
    unit_std,
    multiplier,
    value_std,
    case when unit_std = 'pct' then value_std end as value_pct,
    is_nil,
    is_na_text,
    is_zero,
    concat_ws(
        '|',
        case when unit_std = 'pct' and value_in > 1 then 'pct_given_as_0_100' end,
        case when value_kind = 'text' and value_in is not null then 'numeric_from_text' end,
        case when value_kind = 'duration' and value_std is not null then 'iso_duration_parsed' end,
        case
            when value_kind = 'duration' and value_std is null and not is_nil
                then 'iso_duration_unparsed'
        end,
        case
            when implied_unit_source = 'bridge_next_filing' then 'unit_bridged_from_next_filing'
        end,
        case when implied_unit_source = 'text_unit' then 'unit_from_text' end,
        case when implied_unit_source = 'format_default' then 'unit_format_default' end,
        case when unit_conflict then 'unit_conflict_text_vs_bridge' end,
        case
            when unit_label_effective = 'MtCO2e' or unit_label_effective = 'MtCO2e/INR'
                then 'mtco2e_read_as_metric_tonnes'
        end,
        case when unit_label_effective = 'gCO2e' then 'unit_grams_converted' end,
        case
            when value_in is not null and multiplier is null and value_kind != 'duration'
                then 'unit_not_in_map'
        end,
        case when turnover_scale_applied then 'turnover_scale_corrected' end
    ) as normalisation_flag,
    case
        when turnover_scale_applied then turnover_correction_reason
        when implied_unit_source is not null and multiplier != 1
            then
                'unit ' || unit_label_effective || ' inferred (' || implied_unit_source
                || '); value x' || multiplier
    end as correction_reason
from converted
