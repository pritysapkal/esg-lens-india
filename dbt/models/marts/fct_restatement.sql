-- Restatement tracker: for each company, metric and breakdown, the value a company first filed
-- for year Y against the comparative value for Y filed in the next year's report (Y+1).
--   original_value = CY value of year Y from the filing for Y (latest revision)
--   restated_value = PY value of year Y from the filing for Y+1 (latest revision)
-- Only headline / input / secondary numeric metrics, same breakdown, both after normalisation and
-- overrides. Pairs: FY2022-23 -> FY2023-24, FY2023-24 -> FY2024-25, FY2024-25 -> FY2025-26.
-- Classification order: circular unit -> suspected scale error (> 100x apart) -> unit
-- inconsistency -> from/to zero -> no change (<= 1%) -> material -> minor. The first two are
-- not restatements and are excluded from statistics (is_compared = false).
-- Method and thresholds: docs/restatement_method.md.
-- A restatement is a difference between two filings, not a finding of wrongdoing.

{% set restatement_regex = (
    '\\bre-?stat(ed|ement|ements)\\b|'
    ~ '\\bregroup(ed|ing)\\b|\\breclassif(ied|ication)\\b|'
    ~ '\\brevised\\b.{0,40}\\b(number|figure|data)s?\\b|'
    ~ '\\b(number|figure|data)s?\\b.{0,40}\\brevised\\b'
) %}

with metrics as (
    select
        metric_id,
        unit_type,
        direction
    from {{ ref('dim_metric') }}
    where role in ('headline', 'input', 'secondary')
),

originals as (
    select
        fct.isin,
        fct.symbol,
        fct.metric_id,
        fct.dimension_key,
        fct.value_fiscal_year_label,
        fct.source_filing_id as original_filing_id,
        fct.value_std as original_value,
        fct.unit_resolution_method as original_unit_method,
        fct.is_material
    from {{ ref('fct_esg_value') }} as fct
    where fct.is_latest_value and fct.value_std is not null
),

restated as (
    select
        fct.isin,
        fct.metric_id,
        fct.dimension_key,
        fct.value_fiscal_year_label,
        fct.source_filing_id as restating_filing_id,
        fct.filing_fiscal_year_label as restating_fiscal_year_label,
        fct.value_std as restated_value
    from {{ ref('fct_esg_value') }} as fct
    where
        fct.period_role = 'PY'
        and fct.is_latest_revision_filing
        and fct.value_std is not null
),

text_notes as (
    -- one snippet per filing; whole words only ("afforestation" contains "restat"), and
    -- "revised" only within 40 characters of number / figure / data
    select
        filing_id,
        arg_min(snippet, concept) as stated_reason
    from (
        select
            filing_id,
            concept,
            left(
                regexp_replace(
                    regexp_extract(
                        regexp_replace(text, '\s+', ' ', 'g'),
                        '(?i).{0,120}({{ restatement_regex }}).{0,170}'
                    ),
                    'https?://[^ ]+|www\.[^ ]+', '[link removed]', 'g'
                ),
                300
            ) as snippet
        from {{ ref('stg_text_facts') }}
    )
    where snippet != ''
    group by filing_id
),

paired as (
    select
        originals.isin,
        originals.symbol,
        originals.metric_id,
        originals.dimension_key,
        originals.value_fiscal_year_label,
        originals.original_filing_id,
        restated.restating_filing_id,
        restated.restating_fiscal_year_label,
        originals.original_value,
        restated.restated_value,
        originals.original_unit_method,
        originals.is_material,
        metrics.unit_type,
        metrics.direction
    from originals
    inner join restated
        on
            originals.isin = restated.isin
            and originals.metric_id = restated.metric_id
            and originals.dimension_key = restated.dimension_key
            and originals.value_fiscal_year_label = restated.value_fiscal_year_label
    inner join metrics on originals.metric_id = metrics.metric_id
),

measured as (
    select
        *,
        restated_value - original_value as abs_change,
        case
            when original_value != 0
                then (restated_value - original_value) / abs(original_value)
        end as pct_change,
        case
            when unit_type = 'pct' then restated_value - original_value
        end as pp_change,
        case
            when original_value > 0 and restated_value > 0
                then restated_value / original_value
        end as ratio
    from paired
),

classified as (
    select
        *,
        case
            when original_unit_method = 'bridged-from-next-filing'
                then 'unit_inferred_from_restating_filing'
            when {{ is_scale_error('ratio') }} then 'suspected_scale_error'
            when
                ratio is not null
                and (
                    abs(ratio / 100.0 - 1) <= 0.05 or abs(ratio * 100.0 - 1) <= 0.05
                    or abs(ratio / 1e3 - 1) <= 0.05 or abs(ratio * 1e3 - 1) <= 0.05
                    or abs(ratio / 1e5 - 1) <= 0.05 or abs(ratio * 1e5 - 1) <= 0.05
                    or abs(ratio / 1e6 - 1) <= 0.05 or abs(ratio * 1e6 - 1) <= 0.05
                    or abs(ratio / 1e7 - 1) <= 0.05 or abs(ratio * 1e7 - 1) <= 0.05
                )
                then 'unit_inconsistency'
            when original_value = 0 and restated_value != 0 then 'from_zero'
            when restated_value = 0 and original_value != 0 then 'to_zero'
            when abs_change = 0 or abs(pct_change) <= 0.01 then 'no_change'
            when
                abs(pct_change) > 0.05
                and case
                    when unit_type = 'pct' then abs(pp_change) > 1
                    when unit_type = 'count' then abs(abs_change) >= 2
                    else true
                end
                then 'material'
            else 'minor'
        end as classification
    from measured
),

explained as (
    select
        classified.*,
        company_year.has_comparability_break,
        company_year.comparability_break_reason,
        text_notes.stated_reason as note_snippet
    from classified
    left join {{ ref('dim_company_year') }} as company_year
        on
            classified.isin = company_year.isin
            and classified.restating_fiscal_year_label = company_year.fiscal_year_label
    left join text_notes on classified.restating_filing_id = text_notes.filing_id
),

final as (
    select
        *,
        case
            when
                has_comparability_break
                and (
                    comparability_break_reason like '%merger%'
                    or comparability_break_reason like '%demerger%'
                )
                then 'merger/demerger'
            when has_comparability_break and comparability_break_reason like '%boundary%'
                then 'boundary change'
            when note_snippet is not null then 'possible note (weak)'
        end as explained_by,
        case
            when classification != 'material' then null
            when direction = 'lower_better' then restated_value > original_value
            when direction = 'higher_better' then restated_value < original_value
        end as flatters_trend
    from explained
)

select
    isin,
    symbol,
    metric_id,
    dimension_key,
    value_fiscal_year_label,
    restating_fiscal_year_label,
    original_filing_id,
    restating_filing_id,
    original_value,
    restated_value,
    abs_change,
    pct_change,
    pp_change,
    unit_type,
    direction,
    classification,
    classification not in ('unit_inferred_from_restating_filing', 'suspected_scale_error')
        as is_compared,
    ratio,
    original_unit_method as original_unit_resolution_method,
    explained_by,
    case
        when explained_by = 'possible note (weak)' then note_snippet
    end as stated_reason,
    flatters_trend,
    coalesce(
        classification = 'material' and explained_by is null and flatters_trend, false
    ) as red_flag,
    coalesce(
        classification = 'material'
        and coalesce(explained_by, '') not in ('merger/demerger', 'boundary change')
        and flatters_trend,
        false
    ) as red_flag_strict,
    is_material as is_metric_material
from final
