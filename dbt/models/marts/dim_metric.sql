-- One row per catalogue metric: definition, unit type, direction and disclosure requirement.
-- unit_type: pct | count | quantity | intensity | days | text. A metric keeps the same unit,
-- direction and attribute in every taxonomy version (checked by the catalogue tests).

with catalogue as (
    select
        metric_id,
        min(metric_name) as metric_name,
        min(brsr_core_attribute) as brsr_core_attribute,
        min(role) as role,  -- noqa: RF04
        min(unit_std) as unit_std,
        min(direction) as direction,
        min(value_kind) as value_kind
    from {{ ref('concept_metric_map') }}
    group by metric_id
)

select
    catalogue.metric_id,
    catalogue.metric_name,
    catalogue.brsr_core_attribute,
    catalogue.role,
    catalogue.unit_std,
    case
        when catalogue.unit_std is null then 'text'
        when catalogue.unit_std = 'pct' then 'pct'
        when catalogue.unit_std = 'count' then 'count'
        when catalogue.unit_std = 'days' then 'days'
        when catalogue.unit_std like '%/INR cr' or catalogue.unit_std = 'per_million_hours'
            then 'intensity'
        else 'quantity'
    end as unit_type,
    catalogue.direction,
    catalogue.value_kind,
    requirement.indicator_type,
    requirement.mandatory_from_fy,
    coalesce(requirement.brsr_core, false) as brsr_core,
    cast(
        row_number() over (
            order by catalogue.brsr_core_attribute, catalogue.metric_id
        ) as integer
    ) as sort_order
from catalogue
left join {{ ref('metric_disclosure_requirement') }} as requirement
    on catalogue.metric_id = requirement.metric_id
