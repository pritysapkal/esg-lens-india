-- Real data: the HDFC Bank FY2025-26 filing's comparative (PY) Scope 2 = 284877.91 tCO2e and
-- belongs to FY2024-25.
{{ config(tags=['realdata']) }}

select 'expected PY ghg_scope2_tco2e = 284877.91 labelled FY2024-25' as problem
where (
    select count(*)
    from {{ ref('int_metric_values') }}
    where
        symbol = 'HDFCBANK' and fiscal_year_label = 'FY2025-26' and period_role = 'PY'
        and metric_id = 'ghg_scope2_tco2e' and dimension_key = ''
        and value_std = 284877.91 and value_fiscal_year_label = 'FY2024-25'
        and is_comparative and not is_latest_filing_for_value
) != 1
