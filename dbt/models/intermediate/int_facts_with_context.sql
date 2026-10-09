-- One row per fact (numbers and short text) with its filing, context and unit attached.

with facts as (
    select * from {{ ref('stg_facts') }}
),

filings as (
    select * from {{ ref('stg_filings') }}
),

contexts as (
    select * from {{ ref('stg_contexts') }}
),

units as (
    select * from {{ ref('stg_units') }}
)

select
    facts.fact_id,
    facts.filing_id,
    filings.symbol,
    filings.isin,
    filings.fiscal_year_label,
    filings.reporting_year_label,
    filings.taxonomy_version,
    filings.period_start as filing_period_start,
    filings.period_end as filing_period_end,
    filings.is_non_standard_period,
    facts.sequence,
    facts.concept,
    facts.context_ref,
    contexts.period_type,
    contexts.start_date,
    contexts.end_date,
    contexts.instant_date,
    contexts.dimension_key,
    contexts.has_dimensions,
    facts.unit_ref,
    units.unit_label,
    facts.raw_value,
    facts.value_num,
    facts.value_text,
    facts.decimals,
    facts.decimals_is_inf,
    facts.is_nil,
    facts.is_numeric,
    facts.is_na_text,
    facts.is_zero,
    facts.is_cast_failed
from facts
inner join filings on facts.filing_id = filings.filing_id
inner join contexts
    on
        facts.filing_id = contexts.filing_id
        and facts.context_ref = contexts.context_id
left join units
    on
        facts.filing_id = units.filing_id
        and facts.unit_ref = units.unit_id
