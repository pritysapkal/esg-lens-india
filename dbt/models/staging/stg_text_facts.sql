-- Long text facts (TextBlock concepts or values over 1,000 characters), full text kept.

with text_facts as (
    select * from {{ source('brsr_raw', 'text_facts') }}
)

select
    fact_id,
    filing_id,
    reporting_year_label,
    cast(sequence as integer) as sequence,
    concept,
    context_ref,
    is_nil,
    raw_value as text,
    length(raw_value) as text_length
from text_facts
