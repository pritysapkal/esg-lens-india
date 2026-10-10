-- dim_company_year has one row for every company and financial year that has a filing, and every
-- metric in the catalogue has a disclosure requirement row.
select 'company-year rows differ from filing-years in stg_filings' as problem
where
    (select count(*) from {{ ref('dim_company_year') }})
    != (select count(distinct isin || fiscal_year_label) from {{ ref('stg_filings') }})

union all

select 'metric without disclosure requirement: ' || catalogue.metric_id as problem
from (select distinct metric_id from {{ ref('concept_metric_map') }}) as catalogue
left join {{ ref('metric_disclosure_requirement') }} as requirement
    on catalogue.metric_id = requirement.metric_id
where requirement.metric_id is null
