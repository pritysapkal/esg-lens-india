-- KPI sanity checks, severity warn: lists the company-years that look wrong so a person can
-- review them (they are not necessarily errors in the pipeline; filings contain mistakes).
--  * percentages outside 0-100
--  * waste balance gap above 20% of waste generated
--  * filed vs computed GHG intensity ratio outside 0.9-1.1
{{ config(severity='warn') }}

{% set pct_kpis = [
    'renewable_share_pct', 'waste_recovery_rate_pct', 'female_workforce_pct',
    'female_wage_share_pct', 'female_board_pct', 'attrition_female_pct', 'attrition_male_pct',
    'wellbeing_cost_pct_revenue', 'msme_sourcing_pct', 'posh_complaints_pct_female',
    'rpt_purchases_pct', 'rpt_sales_pct',
] %}

with percentages as (
    select
        symbol,
        fiscal_year_label,
        kpi_name,
        kpi_value,
        'percent outside 0-100' as problem
    from (
        unpivot (
            select
                symbol,
                fiscal_year_label,
                {{ pct_kpis | join(', ') }}
            from {{ ref('fct_company_year') }}
        )
        on {{ pct_kpis | join(', ') }}
        into name kpi_name value kpi_value
    )
    where kpi_value < 0 or kpi_value > 100
),

others as (
    select
        symbol,
        fiscal_year_label,
        'waste_balance_gap_pct' as kpi_name,
        waste_balance_gap_pct as kpi_value,
        'balance gap above 20%' as problem
    from {{ ref('fct_company_year') }}
    where abs(waste_balance_gap_pct) > 20

    union all

    select
        symbol,
        fiscal_year_label,
        'ghg_intensity_filed_vs_computed_ratio' as kpi_name,
        ghg_intensity_filed_vs_computed_ratio as kpi_value,
        'filed vs computed outside 0.9-1.1' as problem
    from {{ ref('fct_company_year') }}
    where
        ghg_intensity_filed_vs_computed_ratio < 0.9
        or ghg_intensity_filed_vs_computed_ratio > 1.1
)

select * from percentages
union all
select * from others
