-- Real data: staging row counts equal the full parsed set of 196 filings (week 3 parser run).
-- Data-independent row-count checks against the sources are in _staging.yml.
{{ config(tags=['realdata']) }}

with counts as (
    select
        (select count(*) from {{ ref('stg_filings') }}) as n_filings,
        (select count(*) from {{ ref('stg_contexts') }}) as n_contexts,
        (select count(*) from {{ ref('stg_units') }}) as n_units,
        (select count(*) from {{ ref('stg_facts') }})
        + (select count(*) from {{ ref('stg_text_facts') }}) as n_facts_all
)

select *
from counts
where
    n_filings != 196
    or n_contexts != 121891
    or n_units != 1714
    or n_facts_all != 419204
