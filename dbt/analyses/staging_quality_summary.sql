-- Data-quality summary of stg_facts, in one long table:
--   section = 'flag_counts'          one row per taxonomy version and flag (item = flag name)
--   section = 'cast_failures_top20'  the 20 most frequent raw values that could not be read as a
--                                    number (item = the raw text), for manual review.
-- Run: dbt show --select staging_quality_summary --limit 200 (from dbt/, see README).

with facts as (
    select
        facts.*,
        filings.taxonomy_version
    from {{ ref('stg_facts') }} as facts
    inner join {{ ref('stg_filings') }} as filings on facts.filing_id = filings.filing_id
),

flag_counts as (
    select
        taxonomy_version,
        count(*) as n_facts,
        count(*) filter (where is_numeric) as n_numeric,
        count(*) filter (where is_nil) as n_is_nil,
        count(*) filter (where is_na_text) as n_is_na_text,
        count(*) filter (where is_cast_failed) as n_is_cast_failed,
        count(*) filter (where is_zero) as n_is_zero
    from facts
    group by taxonomy_version
),

flags_long as (
    unpivot flag_counts
    on n_facts, n_numeric, n_is_nil, n_is_na_text, n_is_cast_failed, n_is_zero
    into name value_name value n
),

cast_failures as (
    select
        raw_value,
        count(*) as n
    from facts
    where is_cast_failed
    group by raw_value
    order by n desc, raw_value asc
    limit 20
)

select
    'flag_counts' as section,
    taxonomy_version,
    value_name as item,
    n
from flags_long
union all
select
    'cast_failures_top20' as section,
    null as taxonomy_version,
    raw_value as item,
    n
from cast_failures
order by section desc, taxonomy_version asc, item asc
