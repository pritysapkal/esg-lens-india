-- Every manual override matches exactly one filing + metric that has values, and its symbol and
-- fiscal year agree with that filing (guards against a mistyped filing_id).
{{ config(tags=['realdata']) }}

with overrides as (
    select * from {{ ref('manual_overrides') }}
),

targets as (
    select
        filing_id,
        metric_id,
        symbol,
        fiscal_year_label,
        count(*) as n_values
    from {{ ref('int_values_normalised') }}
    group by filing_id, metric_id, symbol, fiscal_year_label
),

matches as (
    select
        overrides.override_id,
        overrides.symbol,
        overrides.fiscal_year_label,
        count(targets.filing_id) as n_matches
    from overrides
    left join targets
        on
            overrides.filing_id = targets.filing_id
            and overrides.metric_id = targets.metric_id
            and overrides.symbol = targets.symbol
            and overrides.fiscal_year_label = targets.fiscal_year_label
    group by overrides.override_id, overrides.symbol, overrides.fiscal_year_label
)

select *
from matches
where n_matches != 1
