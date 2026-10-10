-- int_metric_values with company identity and materiality: peer group (dim_company, by ISIN) and
-- is_material (metric_materiality, by peer group and metric). Not material = shown, not ranked.
-- Left joins: every metric value is kept even if a company or peer group is missing.

select
    metric_values.*,  -- noqa: AM04
    dim_company.current_name as company_name,
    dim_company.peer_group,
    metric_materiality.is_material,
    metric_materiality.reason as materiality_reason
from {{ ref('int_metric_values') }} as metric_values
left join {{ ref('dim_company') }} as dim_company
    on metric_values.isin = dim_company.isin
left join {{ ref('metric_materiality') }} as metric_materiality
    on
        dim_company.peer_group = metric_materiality.peer_group
        and metric_values.metric_id = metric_materiality.metric_id
