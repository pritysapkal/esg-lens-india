-- One row per XBRL context: typed period dates plus dimension helpers.

with contexts as (
    select * from {{ source('brsr_raw', 'contexts') }}
)

select
    filing_id,
    context_id,
    reporting_year_label,
    identifier_scheme,
    identifier_value,
    period_type,
    cast(start_date as date) as start_date,
    cast(end_date as date) as end_date,
    cast(instant_date as date) as instant_date,
    coalesce(dimension_key, '') as dimension_key,
    cast(json_array_length(dimensions) as integer) as n_dimensions,
    json_array_length(dimensions) > 0 as has_dimensions,
    dimensions
from contexts
