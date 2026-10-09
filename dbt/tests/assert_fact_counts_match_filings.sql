-- Per filing, the facts in stg_facts + stg_text_facts add up to the parser's own count (n_facts).

with staged as (
    select
        filing_id,
        count(*) as n
    from {{ ref('stg_facts') }}
    group by filing_id
    union all
    select
        filing_id,
        count(*) as n
    from {{ ref('stg_text_facts') }}
    group by filing_id
),

per_filing as (
    select
        filing_id,
        sum(n) as n_staged
    from staged
    group by filing_id
)

select
    filings.filing_id,
    filings.symbol,
    filings.n_facts,
    per_filing.n_staged
from {{ ref('stg_filings') }} as filings
left join per_filing on filings.filing_id = per_filing.filing_id
where filings.n_facts != coalesce(per_filing.n_staged, 0)
