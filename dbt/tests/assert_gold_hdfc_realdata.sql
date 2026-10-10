-- Real data, HDFC Bank FY2025-26 (checked by hand against the filing): Scope 1 = 91,849.5 tCO2e,
-- GHG intensity = (Scope 1 + Scope 2) / (turnover / 1e7) within 0.1%, renewable share 15.86%
-- (345,972.88 / 2,181,402), female wage share 20.36%. And the FY2024-25 Scope 2 value
-- 284,877.91 appears as the restated value in the restatement tracker.
{{ config(tags=['realdata']) }}

with hdfc as (
    select *
    from {{ ref('fct_company_year') }}
    where symbol = 'HDFCBANK' and fiscal_year_label = 'FY2025-26'
)

select 'HDFC FY2025-26 row missing' as problem
where (select count(*) from hdfc) != 1

union all

select 'ghg_s1_tco2e is ' || cast(ghg_s1_tco2e as varchar) as problem
from hdfc
where abs(ghg_s1_tco2e - 91849.5) > 0.01

union all

select 'ghg intensity is ' || cast(ghg_intensity_tco2e_per_cr as varchar) as problem
from hdfc
where
    abs(
        ghg_intensity_tco2e_per_cr
        / ((91849.5 + 236495.41) / (3700546500000 / 1e7)) - 1
    ) > 0.001

union all

select 'renewable_share_pct is ' || cast(renewable_share_pct as varchar) as problem
from hdfc
where abs(renewable_share_pct - 345972.88 / 2181402 * 100) > 0.01

union all

select 'female_wage_share_pct is ' || cast(female_wage_share_pct as varchar) as problem
from hdfc
where abs(female_wage_share_pct - 20.36) > 0.001

union all

select 'HDFC FY2024-25 scope 2 restated value 284877.91 not found' as problem
where
    (
        select count(*)
        from {{ ref('fct_restatement') }}
        where
            symbol = 'HDFCBANK'
            and metric_id = 'ghg_scope2_tco2e'
            and value_fiscal_year_label = 'FY2024-25'
            and abs(restated_value - 284877.91) < 0.01
    ) != 1
