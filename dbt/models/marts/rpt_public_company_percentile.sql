-- PUBLIC position of each company within its ranking group, per KPI and financial year: the
-- percentile (100 = best), the rank (1 = best), how many companies the group has with a value,
-- whether the company is ranked and, if not, why. From fct_company_kpi_percentile.
-- The position is ours and public for every KPI; the KPI's own value is shown only when the
-- kpi_catalogue marks the KPI public_safe (a value we compute, such as an intensity). For a
-- filed value (a filed percentage, LTIFR, days payable, ...) kpi_value_public stays empty
-- (docs/publication_policy.md). assert_public_models_safe checks both on every build.

with positions as (
    select
        percentile.isin,
        percentile.fiscal_year_label,
        percentile.kpi_name,
        percentile.ranking_group,
        percentile.value,
        percentile.group_n,
        percentile.percentile_in_group,
        percentile.percentile_null_reason,
        catalogue.label as kpi_label,
        catalogue.unit as kpi_unit,
        catalogue.direction,
        coalesce(catalogue.public_safe, false) as value_is_public
    from {{ ref('fct_company_kpi_percentile') }} as percentile
    left join {{ ref('kpi_catalogue') }} as catalogue
        on
            percentile.kpi_name = catalogue.kpi_name
            and catalogue.metric_type = 'company_value'
    where percentile.value is not null
)

select
    positions.isin,
    company.display_name,
    positions.fiscal_year_label,
    positions.kpi_name,
    positions.kpi_label,
    positions.kpi_unit,
    positions.direction,
    company.peer_group,
    company.sector_group,
    positions.ranking_group,
    positions.percentile_in_group,
    -- 1 = best; companies with the same value share the better rank (as the percentile does)
    case
        when positions.percentile_in_group is not null
            then cast(
                rank() over (
                    partition by
                        positions.ranking_group,
                        positions.fiscal_year_label,
                        positions.kpi_name,
                        positions.percentile_in_group is null
                    order by positions.percentile_in_group desc
                ) as integer
            )
    end as rank_in_group,
    positions.group_n as n_in_group,
    positions.percentile_in_group is not null as is_ranked,
    positions.percentile_null_reason as reason_not_ranked,
    case when positions.value_is_public then positions.value end as kpi_value_public
from positions
left join {{ ref('dim_company') }} as company on positions.isin = company.isin
