-- Real data: NESTLEIND has exactly one 15-month year (2023-01-01..2024-03-31) and it is
-- annualised with factor 0.8; every other NESTLEIND year has factor 1.
{{ config(tags=['realdata']) }}

select
    symbol,
    fiscal_year_label,
    period_months,
    annualisation_factor
from {{ ref('dim_company_year') }}
where
    symbol = 'NESTLEIND'
    and round(annualisation_factor, 4) != case when period_months = 15 then 0.8 else 1.0 end
