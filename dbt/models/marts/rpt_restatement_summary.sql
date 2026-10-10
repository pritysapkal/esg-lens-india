-- Restatement summary at four levels: overall, by metric, by peer group, by company.
-- Pairs where the original unit was inferred from the restating filing (circular) are excluded
-- from every statistic and counted in n_excluded_circular. Shares are of compared pairs, except
-- the "of material" shares, which are of material restatements.

{% set levels = {
    'overall': "'all'",
    'metric': 'metric_id',
    'peer_group': "coalesce(peer_group, '(none)')",
    'company': 'symbol',
} %}

with pairs as (
    select
        restatement.*,
        company.peer_group
    from {{ ref('fct_restatement') }} as restatement
    left join {{ ref('dim_company') }} as company on restatement.isin = company.isin
)

{% for level, key in levels.items() %}
    {{ 'union all' if not loop.first else '' }}
    select
        '{{ level }}' as level,  -- noqa: RF04
        {{ key }} as group_key,
        cast(count(*) filter (where is_compared) as integer) as n_pairs,
        cast(count(*) filter (where not is_compared) as integer) as n_excluded_circular,
        cast(count(*) filter (where classification = 'no_change') as integer) as n_no_change,
        cast(count(*) filter (where classification = 'minor') as integer) as n_minor,
        cast(count(*) filter (where classification = 'material') as integer) as n_material,
        cast(count(*) filter (where classification = 'unit_inconsistency') as integer)
            as n_unit_inconsistency,
        cast(count(*) filter (where classification in ('from_zero', 'to_zero')) as integer)
            as n_from_to_zero,
        count(*) filter (where classification = 'no_change') * 100.0
        / nullif(count(*) filter (where is_compared), 0) as pct_no_change,
        count(*) filter (where classification = 'minor') * 100.0
        / nullif(count(*) filter (where is_compared), 0) as pct_minor,
        count(*) filter (where classification = 'material') * 100.0
        / nullif(count(*) filter (where is_compared), 0) as pct_material,
        cast(
            count(*) filter (where classification = 'material' and explained_by is null) as integer
        )
            as n_material_unexplained,
        count(*) filter (where classification = 'material' and explained_by is null) * 100.0
        / nullif(count(*) filter (where classification = 'material'), 0)
            as pct_material_unexplained,
        cast(count(*) filter (where classification = 'material' and flatters_trend) as integer)
            as n_material_flattering,
        count(*) filter (where classification = 'material' and flatters_trend) * 100.0
        / nullif(count(*) filter (where classification = 'material'), 0) as pct_material_flattering,
        cast(count(*) filter (where red_flag) as integer) as n_red_flags,
        cast(count(distinct isin) filter (where is_compared) as integer) as n_companies,
        cast(count(distinct isin) filter (where classification = 'material') as integer)
            as n_companies_with_material,
        count(distinct isin) filter (where classification = 'material') * 100.0
        / nullif(count(distinct isin) filter (where is_compared), 0) as pct_companies_with_material
    from pairs
    {% if level != 'overall' %}group by {{ key }}{% endif %}
{% endfor %}
