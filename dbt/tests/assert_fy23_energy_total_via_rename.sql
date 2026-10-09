-- Real data: every FY2022-23 filing has a current-year energy_total_gj, which the 2021/2023
-- taxonomies file under the renamed concept TotalEnergyConsumption.
{{ config(tags=['realdata']) }}

with fy23 as (
    select filing_id from {{ ref('stg_filings') }}
    where fiscal_year_label = 'FY2022-23'
),

energy as (
    select distinct filing_id
    from {{ ref('int_metric_values') }}
    where
        fiscal_year_label = 'FY2022-23' and period_role = 'CY' and dimension_key = ''
        and metric_id = 'energy_total_gj' and concept = 'TotalEnergyConsumption'
        and value_std is not null
)

select fy23.filing_id
from fy23
where fy23.filing_id not in (select energy.filing_id from energy)
