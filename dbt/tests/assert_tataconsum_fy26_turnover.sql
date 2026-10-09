-- Real data: TATACONSUM FY2025-26 filed turnover 14700.05 (crore) -> ~1.47e11 INR.
{{ config(tags=['realdata']) }}

select 'expected TATACONSUM FY2025-26 turnover_inr ~ 1.47e11 with scale_applied' as problem
where (
    select count(*)
    from {{ ref('int_turnover_corrected') }}
    where
        symbol = 'TATACONSUM' and fiscal_year_label = 'FY2025-26'
        and scale_applied and scale_name = 'crore'
        and turnover_inr between 1.46e11 and 1.48e11
) != 1
