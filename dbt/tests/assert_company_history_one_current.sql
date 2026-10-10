-- Exactly one current row per company, and every company in dim_company has history.
select
    dim_company.isin,
    count(*) filter (where history.is_current) as n_current
from {{ ref('dim_company') }} as dim_company
left join {{ ref('dim_company_history') }} as history on dim_company.isin = history.isin
group by dim_company.isin
having count(*) filter (where history.is_current) != 1
