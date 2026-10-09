-- After an override, the corrected current-year value is within 3x of the same company's value
-- for each adjacent financial year (previous and next filing), so the multiplier is plausible.
{{ config(tags=['realdata']) }}

with current_values as (
    select
        symbol,
        metric_id,
        fiscal_year_label,
        cast(substr(fiscal_year_label, 3, 4) as integer) as fy_start,
        value_std,
        override_id
    from {{ ref('int_metric_values') }}
    where is_latest_filing_for_value and dimension_key = '' and value_std is not null
),

overridden as (
    select * from current_values
    where override_id is not null
)

select
    overridden.override_id,
    overridden.symbol,
    overridden.metric_id,
    overridden.fiscal_year_label,
    overridden.value_std,
    adjacent.fiscal_year_label as adjacent_year,
    adjacent.value_std as adjacent_value
from overridden
inner join current_values as adjacent
    on
        overridden.symbol = adjacent.symbol
        and overridden.metric_id = adjacent.metric_id
        and abs(overridden.fy_start - adjacent.fy_start) = 1
where
    adjacent.value_std = 0
    or overridden.value_std / adjacent.value_std not between 1.0 / 3 and 3
