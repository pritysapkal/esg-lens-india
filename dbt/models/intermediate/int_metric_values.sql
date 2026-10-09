-- Catalogue metrics, one row per value: normalised value, period role and source filing.
-- Only the breakdowns allowed for the metric are kept (allowed_dimension_axes in the catalogue);
-- company-wide values (no breakdown) are always kept.
-- is_latest_filing_for_value: the CY value from the latest filing for that company and year.
-- PY / PY2 values are comparatives as filed a year later (input for the restatement tracker).

{{ config(materialized='table') }}

with values_normalised as (
    select * from {{ ref('int_values_normalised') }}
),

allowed as (
    select *
    from values_normalised
    where
        dimension_key = ''
        or list_has_all(
            string_split(allowed_dimension_axes, '|'), {{ dimension_axes('dimension_key') }}
        )
),

filings_in_scope as (
    select distinct
        filing_id,
        symbol,
        fiscal_year_label,
        filing_period_end
    from allowed
),

latest_filing as (
    select
        filing_id,
        row_number() over (
            partition by symbol, fiscal_year_label
            order by filing_period_end desc, filing_id desc
        ) = 1 as is_latest
    from filings_in_scope
)

select
    allowed.fact_id,
    allowed.symbol,
    allowed.isin,
    allowed.fiscal_year_label,
    allowed.value_fiscal_year_label,
    allowed.period_role,
    allowed.metric_id,
    allowed.role,
    allowed.dimension_key,
    allowed.value_std,
    allowed.value_std_auto,
    allowed.override_id,
    allowed.unit_std,
    allowed.value_pct,
    allowed.value_text,
    allowed.raw_value,
    allowed.value_num,
    allowed.unit_label,
    allowed.is_nil,
    allowed.is_na_text,
    allowed.is_zero,
    allowed.normalisation_flag,
    allowed.correction_reason,
    allowed.concept,
    allowed.taxonomy_version,
    allowed.value_period_end,
    allowed.filing_id,
    allowed.period_role = 'CY' and latest_filing.is_latest as is_latest_filing_for_value,
    allowed.period_role in ('PY', 'PY2', 'INSTANT_PY') as is_comparative
from allowed
inner join latest_filing on allowed.filing_id = latest_filing.filing_id
