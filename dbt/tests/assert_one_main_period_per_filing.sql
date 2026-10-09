-- Every filing has exactly one main period: a period end date, and a main context that is a
-- company-wide (no dimensions) duration whose dates equal the filing's period. It must also be
-- the only distinct company-wide period ending on that latest date (otherwise "main" is ambiguous).

with filings as (
    select * from {{ ref('stg_filings') }}
),

contexts as (
    select * from {{ ref('stg_contexts') }}
),

company_wide as (
    select
        filing_id,
        start_date,
        end_date
    from contexts
    where period_type = 'duration' and not has_dimensions
),

latest_periods as (
    select
        company_wide.filing_id,
        count(distinct company_wide.start_date) as n_periods_ending_latest
    from company_wide
    where
        company_wide.end_date = (
            select max(c2.end_date) from company_wide as c2
            where c2.filing_id = company_wide.filing_id
        )
    group by company_wide.filing_id
)

select
    filings.filing_id,
    filings.symbol,
    filings.period_end,
    latest_periods.n_periods_ending_latest,
    main_ctx.context_id as main_context_found
from filings
left join contexts as main_ctx
    on
        filings.filing_id = main_ctx.filing_id
        and filings.main_context_id = main_ctx.context_id
        and main_ctx.period_type = 'duration'
        and not main_ctx.has_dimensions
        and filings.period_start = main_ctx.start_date
        and filings.period_end = main_ctx.end_date
left join latest_periods on filings.filing_id = latest_periods.filing_id
where
    filings.period_end is null
    or main_ctx.context_id is null
    or coalesce(latest_periods.n_periods_ending_latest, 0) != 1
