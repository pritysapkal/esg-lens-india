-- Numeric and short text facts: raw_value kept unchanged, plus a typed number (value_num) for
-- numeric facts, the text for non-numeric facts, parsed decimals and data-quality flags.
-- No business logic here: periods, units and metric mapping are interpreted downstream.

{{ config(materialized='table') }}

with facts as (
    select * from {{ source('brsr_raw', 'facts') }}
),

typed as (
    select
        fact_id,
        filing_id,
        reporting_year_label,
        cast(sequence as integer) as sequence,
        concept,
        namespace,
        prefix,
        context_ref,
        unit_ref,
        raw_value,
        is_nil,
        is_numeric,
        decimals as decimals_raw,
        case
            when is_numeric and not is_nil then try_cast(raw_value as double)
        end as value_num,
        case when not is_numeric then raw_value end as value_text,
        case
            when upper(trim(decimals)) = 'INF' then null
            else try_cast(decimals as integer)
        end as decimals,
        coalesce(upper(trim(decimals)) = 'INF', false) as decimals_is_inf,
        {{ is_na_text('raw_value') }} as is_na_text
    from facts
)

select
    *,
    is_numeric and not is_nil and not is_na_text and value_num is null as is_cast_failed,
    coalesce(value_num = 0, false) as is_zero
from typed
