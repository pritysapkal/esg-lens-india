-- NSE BRSR listing, typed. The NSE URLs (pdf_url, xbrl_url) are dropped on purpose: published
-- outputs must not link to NSE filings (docs/adr/0002). The file name identifies the filing.

with listing as (
    select * from {{ source('intake', 'listing') }}
),

universe as (
    select distinct trim(symbol) as symbol from {{ source('intake', 'universe') }}
),

manifest as (
    select distinct filing_id from {{ source('intake', 'manifest') }}
)

select
    listing.filing_id,
    listing.symbol,
    listing.company_name,
    listing.reporting_year_label,
    listing.is_non_standard_period,
    listing.xbrl_file_name,
    listing.source_file,
    cast(listing.fy_from as integer) as fy_from,
    cast(listing.fy_to as integer) as fy_to,
    cast(listing.submission_date as date) as submission_date,
    cast(listing.revision_date as date) as revision_date,
    universe.symbol is not null as in_universe,
    manifest.filing_id is not null as is_received
from listing
left join universe on listing.symbol = universe.symbol
left join manifest on listing.filing_id = manifest.filing_id
