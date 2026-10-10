-- One row per filing with its place among the filings of the same company and financial year.
-- NSE lists a revision date when a company re-files; the newest filing of a company-year is the
-- latest revision and the only one gold models use. filed_date is the date of the document held:
-- the revision date if there is one, else the submission date.

with filings as (
    select
        filing_id,
        isin,
        symbol,
        fiscal_year_label,
        period_end
    from {{ ref('stg_filings') }}
),

listing as (
    select
        filing_id,
        submission_date,
        revision_date
    from {{ ref('stg_listing') }}
),

dated as (
    select
        filings.*,
        listing.submission_date,
        listing.revision_date,
        coalesce(listing.revision_date, listing.submission_date) as filed_date
    from filings
    left join listing on filings.filing_id = listing.filing_id
)

select
    filing_id,
    isin,
    symbol,
    fiscal_year_label,
    submission_date,
    revision_date,
    filed_date,
    revision_date is not null as has_revision_date,
    count(*) over (partition by isin, fiscal_year_label) as n_filings_in_year,
    row_number() over (
        partition by isin, fiscal_year_label
        order by filed_date desc nulls last, period_end desc, filing_id desc
    ) as revision_rank,
    row_number() over (
        partition by isin, fiscal_year_label
        order by filed_date desc nulls last, period_end desc, filing_id desc
    ) = 1 as is_latest_revision
from dated
