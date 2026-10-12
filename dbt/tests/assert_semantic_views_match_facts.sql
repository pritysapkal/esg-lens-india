-- The views of the semantic layer must hold exactly the rows of the gold tables they read: a
-- lost or repeated row would make a MetricFlow metric differ from the same figure in SQL.
-- Rows returned are violations.

with counts as (
    select
        'sem_company_year' as semantic_view,
        (select count(*) from {{ ref('sem_company_year') }}) as n_view,
        (select count(*) from {{ ref('fct_company_year') }}) as n_fact
    union all
    select
        'sem_disclosure_quality' as semantic_view,
        (select count(*) from {{ ref('sem_disclosure_quality') }}) as n_view,
        (select count(*) from {{ ref('fct_disclosure_quality') }}) as n_fact
    union all
    select
        'sem_restatement' as semantic_view,
        (select count(*) from {{ ref('sem_restatement') }}) as n_view,
        (select count(*) from {{ ref('fct_restatement') }}) as n_fact
    union all
    select
        'sem_company' as semantic_view,
        (select count(*) from {{ ref('sem_company') }}) as n_view,
        (select count(*) from {{ ref('dim_company') }}) as n_fact
)

select *
from counts
where n_view != n_fact
