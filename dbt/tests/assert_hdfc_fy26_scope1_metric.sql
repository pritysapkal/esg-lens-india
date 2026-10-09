-- Real data: HDFC Bank FY2025-26, current year, company-wide Scope 1 = 91849.5 tCO2e.
{{ config(tags=['realdata']) }}

select 'expected one ghg_scope1_tco2e = 91849.5 tCO2e' as problem
where (
    select count(*)
    from {{ ref('int_metric_values') }}
    where
        symbol = 'HDFCBANK' and fiscal_year_label = 'FY2025-26' and period_role = 'CY'
        and metric_id = 'ghg_scope1_tco2e' and dimension_key = ''
        and value_std = 91849.5 and unit_std = 'tCO2e'
) != 1
