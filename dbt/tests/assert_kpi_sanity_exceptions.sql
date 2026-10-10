-- KPI sanity checks. A finding fails the build unless it is listed in the seed
-- known_kpi_exceptions (reviewed and accepted by a person). Filings contain mistakes, so findings
-- are expected; the point is that every one of them has been looked at once, and a NEW one stops
-- the build instead of drowning in a warning list.
--  * pct_outside_0_100:<kpi>                        a percentage below 0 or above 100
--  * waste_balance_gap_over_20pct                   generated - recovered - disposed > 20%
--  * ghg_intensity_filed_vs_computed_outside_0.9_1.1  filed intensity far from our own
-- To accept a new finding: add a row to dbt/seeds/known_kpi_exceptions.csv with the reason.

{% set pct_kpis = [
    'renewable_share_pct', 'waste_recovery_rate_pct', 'female_workforce_pct',
    'female_wage_share_pct', 'female_board_pct', 'attrition_female_pct', 'attrition_male_pct',
    'wellbeing_cost_pct_revenue', 'msme_sourcing_pct', 'posh_complaints_pct_female',
    'rpt_purchases_pct', 'rpt_sales_pct',
] %}

with percentages as (
    select
        isin,
        symbol,
        fiscal_year_label,
        'pct_outside_0_100:' || kpi_name as check_name,
        kpi_value
    from (
        unpivot (
            select
                isin,
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
        isin,
        symbol,
        fiscal_year_label,
        'waste_balance_gap_over_20pct' as check_name,
        waste_balance_gap_pct as kpi_value
    from {{ ref('fct_company_year') }}
    where abs(waste_balance_gap_pct) > 20

    union all

    select
        isin,
        symbol,
        fiscal_year_label,
        'ghg_intensity_filed_vs_computed_outside_0.9_1.1' as check_name,
        ghg_intensity_filed_vs_computed_ratio as kpi_value
    from {{ ref('fct_company_year') }}
    where
        ghg_intensity_filed_vs_computed_ratio < 0.9
        or ghg_intensity_filed_vs_computed_ratio > 1.1
),

findings as (
    select * from percentages
    union all
    select * from others
)

select findings.*
from findings
left join {{ ref('known_kpi_exceptions') }} as accepted
    on
        findings.isin = accepted.isin
        and findings.fiscal_year_label = accepted.fiscal_year_label
        and findings.check_name = accepted.check_name
where accepted.isin is null
