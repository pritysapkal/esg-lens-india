-- Intake manifest, typed: one row per XBRL file received and filed into data/raw/xbrl.

with manifest as (
    select * from {{ source('intake', 'manifest') }}
)

select
    filing_id,
    symbol,
    isin,
    isin_source,
    reporting_year_label,
    taxonomy_version,
    entity_identifier,
    entity_identifier_scheme,
    file_name,
    path as file_path,
    sha256,
    cast(bytes as bigint) as file_bytes,
    cast(received_at as timestamptz) as received_at,
    cast(matched_listing as boolean) as matched_listing
from manifest
