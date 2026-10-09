-- The catalogue maps a concept in EVERY taxonomy version whose filings use it: if a concept that
-- the catalogue knows shows up in a version without a catalogue row, it would be silently lost.

with catalogue as (
    select * from {{ ref('concept_metric_map') }}
),

filed as (
    select distinct
        filings.taxonomy_version,
        facts.concept
    from {{ ref('stg_facts') }} as facts
    inner join {{ ref('stg_filings') }} as filings on facts.filing_id = filings.filing_id
    where facts.concept in (select catalogue.concept from catalogue)
)

select filed.*
from filed
left join catalogue
    on
        filed.taxonomy_version = catalogue.taxonomy_version
        and filed.concept = catalogue.concept
where catalogue.concept is null
