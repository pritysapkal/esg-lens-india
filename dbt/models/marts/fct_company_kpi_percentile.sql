-- Each company's position within its ranking group for each comparable KPI and year.
-- percentile_in_group is 0-100 and direction-aware: 100 = best in the group (highest value for
-- higher-is-better KPIs, lowest for lower-is-better). Method: percent rank
-- ((rank - 1) / (n - 1)), ties share the lower rank. Only given when the group has at least 5
-- companies with a value, the KPI is material for the group, and the KPI has a direction;
-- otherwise null with percentile_null_reason. A waste recovery rate above 100% (flag
-- waste_recovery_over_100) keeps its value but is not ranked and does not count in the group.

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
            coalesce(kpi_flags, '') as kpi_flags,
            {{ kpis | join(', ') }}
        from {{ ref('fct_company_year') }}
    )
    on {{ kpis | join(', ') }}
    into name kpi_name value kpi_value
),

with_meta as (
    select
        long.*,
        kpi_catalogue.direction,
        long.kpi_name = 'waste_recovery_rate_pct'
        and contains(long.kpi_flags, 'waste_recovery_over_100') as is_flagged_value,
        coalesce(metric_materiality.is_material, false) as is_material
    from long
    inner join {{ ref('kpi_catalogue') }} as kpi_catalogue
        on long.kpi_name = kpi_catalogue.kpi_name
    left join {{ ref('metric_materiality') }} as metric_materiality
        on
            long.peer_group = metric_materiality.peer_group
            and kpi_catalogue.materiality_metric_id = metric_materiality.metric_id
),

rankable as (
    select
        *,
        case when not is_flagged_value then kpi_value end as rank_value
    from with_meta
),

scored as (
    select
        *,
        count(rank_value) over (
            partition by ranking_group, fiscal_year_label, kpi_name
        ) as group_n,
        bool_and(is_material) over (
            partition by ranking_group, fiscal_year_label, kpi_name
        ) as group_material,
        case
            when direction = 'higher_better'
                then percent_rank() over (
                    partition by ranking_group, fiscal_year_label, kpi_name, rank_value is null
                    order by rank_value asc
                )
            else percent_rank() over (
                partition by ranking_group, fiscal_year_label, kpi_name, rank_value is null
                order by rank_value desc
            )
        end as rank_fraction
    from rankable
)

select
    isin,
    fiscal_year_label,
    kpi_name,
    ranking_group,
    kpi_value as value,  -- noqa: RF04
    cast(group_n as integer) as group_n,
    case
        when
            rank_value is not null
            and group_n >= 5
            and group_material
            and direction in ('higher_better', 'lower_better')
            then round(rank_fraction * 100, 1)
    end as percentile_in_group,
    case
        when ranking_group is null then 'no_group'
        when kpi_value is null then 'no_value'
        when is_flagged_value then 'flagged_value'
        when not group_material then 'not_material'
        when direction not in ('higher_better', 'lower_better') then 'no_direction'
        when group_n < 5 then 'group_n_lt_5'
    end as percentile_null_reason
from scored
