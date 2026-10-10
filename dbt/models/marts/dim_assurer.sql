-- One row per assurance / assessment provider named in the filings, spelling variants merged
-- (see int_company_year_assurers for the merging rules).

with named as (
    select * from {{ ref('int_company_year_assurers') }}
),

id_counts as (
    select
        assurer_key,
        id_clean,
        count(*) as n
    from named
    where id_clean != ''
    group by assurer_key, id_clean
),

main_id as (
    select
        assurer_key,
        arg_max(id_clean, n) as assurer_id
    from id_counts
    group by assurer_key
),

summary as (
    select
        assurer_key,
        min(assurer_name) as assurer_name,
        count(distinct isin || fiscal_year_label) as n_company_years,
        count(distinct isin) as n_companies,
        min(fiscal_year_label) as first_fy,
        max(fiscal_year_label) as last_fy,
        count(distinct name_filed) as n_name_variants
    from named
    group by assurer_key
)

select
    summary.assurer_key,
    summary.assurer_name,
    main_id.assurer_id,
    cast(summary.n_company_years as integer) as n_company_years,
    cast(summary.n_companies as integer) as n_companies,
    summary.first_fy,
    summary.last_fy,
    cast(summary.n_name_variants as integer) as n_name_variants
from summary
left join main_id on summary.assurer_key = main_id.assurer_key
