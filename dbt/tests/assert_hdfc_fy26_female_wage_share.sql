-- Real data: HDFC Bank FY2025-26 share of wages paid to women = 0.2036 filed -> 20.36 %.
{{ config(tags=['realdata']) }}

select 'expected female_wage_share_pct = 20.36' as problem
where (
    select count(*)
    from {{ ref('int_metric_values') }}
    where
        symbol = 'HDFCBANK' and fiscal_year_label = 'FY2025-26' and period_role = 'CY'
        and metric_id = 'female_wage_share_pct' and dimension_key = ''
        and value_pct = 20.36 and raw_value = '0.2036'
) != 1
