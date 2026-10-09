-- Real data: Nestle India's FY2023-24 filing covers 15 months (2023-01-01 to 2024-03-31) after
-- it moved from calendar years to April-March, and must be flagged as non-standard.
{{ config(tags=['realdata']) }}

select 'NESTLEIND 15-month filing missing or not flagged' as problem
where not exists (
    select 1
    from {{ ref('stg_filings') }}
    where
        symbol = 'NESTLEIND'
        and period_start = date '2023-01-01'
        and period_end = date '2024-03-31'
        and period_months = 15
        and is_non_standard_period
)
