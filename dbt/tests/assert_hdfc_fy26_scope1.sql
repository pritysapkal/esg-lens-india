-- Real data: HDFC Bank FY2025-26 reports TotalScope1Emissions = 91849.5 tCO2e for the current
-- year, company-wide (no dimensions). Checked by hand (docs/parser_validation.md).
{{ config(tags=['realdata']) }}

with hdfc_value as (
    select facts.value_num
    from {{ ref('stg_facts') }} as facts
    inner join {{ ref('stg_filings') }} as filings on facts.filing_id = filings.filing_id
    inner join {{ ref('stg_contexts') }} as contexts
        on
            facts.filing_id = contexts.filing_id
            and facts.context_ref = contexts.context_id
    where
        filings.symbol = 'HDFCBANK'
        and filings.fiscal_year_label = 'FY2025-26'
        and facts.concept = 'TotalScope1Emissions'
        and not contexts.has_dimensions
        and contexts.start_date = filings.period_start
        and contexts.end_date = filings.period_end
)

select 'expected exactly one value 91849.5' as problem
where
    (
        select count(*) from hdfc_value
        where value_num = 91849.5
    ) != 1
    or (select count(*) from hdfc_value) != 1
