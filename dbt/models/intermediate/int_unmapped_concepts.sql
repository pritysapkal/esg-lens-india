-- Numeric concepts that carry values but are not in the metric catalogue, per taxonomy version.
-- For review (candidates for future metrics), not errors.

with facts as (
    select * from {{ ref('int_facts_with_context') }}
    where is_numeric and value_num is not null
),

metric_map as (
    select * from {{ ref('concept_metric_map') }}
)

select
    facts.taxonomy_version,
    facts.concept,
    count(*) as n_facts,
    count(distinct facts.filing_id) as n_filings,
    count(*) filter (where facts.value_num != 0) as n_nonzero,
    list(distinct facts.unit_label order by facts.unit_label) as unit_labels
from facts
left join metric_map
    on
        facts.taxonomy_version = metric_map.taxonomy_version
        and facts.concept = metric_map.concept
where metric_map.concept is null
group by facts.taxonomy_version, facts.concept
