-- Distribution of each comparable KPI per ranking group and year: n, median, quartiles, min,
-- max. Only KPIs whose metric is material for the group (for every peer group inside it) appear;
-- KPIs are those of the kpi_catalogue seed. Levels are not filtered for comparability breaks.
-- has_min_n says whether the group has at least 5 companies with a value.

{% set kpis = [
    'ghg_intensity_tco2e_per_cr', 'renewable_share_pct', 'energy_intensity_gj_per_cr',
    'water_intensity_kl_per_cr', 'waste_intensity_t_per_cr', 'waste_recovery_rate_pct',
    'ltifr_employees', 'ltifr_workers', 'fatalities_per_10k_workforce', 'female_workforce_pct',
    'female_wage_share_pct', 'pay_equity_gap_pp', 'attrition_gap_pp',
    'wellbeing_cost_pct_revenue', 'msme_sourcing_pct', 'days_payable', 'rpt_purchases_pct',
    'rpt_sales_pct', 'posh_complaints_pct_female',
] %}

with long as (
    unpivot (
        select
            isin,
            fiscal_year_label,
            ranking_group,
            peer_group,
            {{ kpis | join(', ') }}
        from {{ ref('fct_company_year') }}
    )
    on {{ kpis | join(', ') }}
    into name kpi_name value kpi_value
),

with_meta as (
    select
        long.*,
        kpi_catalogue.label as kpi_label,
        kpi_catalogue.unit_type,
        kpi_catalogue.direction,
        coalesce(metric_materiality.is_material, false) as is_material
    from long
    inner join {{ ref('kpi_catalogue') }} as kpi_catalogue
        on long.kpi_name = kpi_catalogue.kpi_name
    left join {{ ref('metric_materiality') }} as metric_materiality
        on
            long.peer_group = metric_materiality.peer_group
            and kpi_catalogue.materiality_metric_id = metric_materiality.metric_id
    where long.ranking_group is not null
)

select
    ranking_group,
    fiscal_year_label,
    kpi_name,
    any_value(kpi_label) as kpi_label,
    any_value(unit_type) as unit_type,
    any_value(direction) as direction,
    cast(count(distinct isin) as integer) as n_companies_in_group,
    cast(count(kpi_value) as integer) as n_companies,
    count(kpi_value) >= 5 as has_min_n,
    quantile_cont(kpi_value, 0.5) as median_value,
    quantile_cont(kpi_value, 0.25) as p25_value,
    quantile_cont(kpi_value, 0.75) as p75_value,
    min(kpi_value) as min_value,
    max(kpi_value) as max_value
from with_meta
group by ranking_group, fiscal_year_label, kpi_name
having bool_and(is_material)
