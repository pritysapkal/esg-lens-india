-- Restatement summary: overall, by metric, by peer group, by company, plus a block comparable
-- with published surveys. Two classes are not restatements and are excluded from every statistic:
-- circular pairs (original unit inferred from the restating filing, n_excluded_circular) and
-- suspected scale errors (values more than 100x apart, n_excluded_scale_error).
-- Shares are of compared pairs, except the "of material" shares (of material restatements).
-- level 'kpmg_comparable': headline totals only (Scope 1, Scope 2, total energy, water withdrawal,
-- waste generated; company-wide values), for the FY2023-24 -> FY2024-25 pair and for all pairs.
-- KPMG 2026 reports 45 of 94 NIFTY 100 companies (about 48%) revising prior-year BRSR figures;
-- definitions still differ (their universe, metrics and materiality rule are not ours).

{% set headline_filter %}
    metric_id in (
        'ghg_scope1_tco2e', 'ghg_scope2_tco2e', 'energy_total_gj', 'water_withdrawal_kl',
        'waste_generated_t'
    )
    and dimension_key = ''
{% endset %}

{% set blocks = [
    {'level': 'overall', 'key': "'all'", 'where': 'true', 'grouped': false},
    {'level': 'metric', 'key': 'metric_id', 'where': 'true', 'grouped': true},
    {'level': 'peer_group', 'key': "coalesce(peer_group, '(none)')", 'where': 'true', 'grouped': true},
    {'level': 'company', 'key': 'symbol', 'where': 'true', 'grouped': true},
    {
        'level': 'kpmg_comparable',
        'key': "'FY2023-24 -> FY2024-25'",
        'where': headline_filter ~ " and value_fiscal_year_label = 'FY2023-24'",
        'grouped': false,
    },
    {
        'level': 'kpmg_comparable',
        'key': "'all pairs'",
        'where': headline_filter,
        'grouped': false,
    },
] %}

with pairs as (
    select
        restatement.*,
        company.peer_group
    from {{ ref('fct_restatement') }} as restatement
    left join {{ ref('dim_company') }} as company on restatement.isin = company.isin
)

{% for block in blocks %}
    {{ 'union all' if not loop.first else '' }}
    select
        '{{ block.level }}' as level,  -- noqa: RF04
        {{ block.key }} as group_key,
        cast(count(*) filter (where is_compared) as integer) as n_pairs,
        cast(
            count(*) filter (where classification = 'unit_inferred_from_restating_filing')
            as integer
        ) as n_excluded_circular,
        cast(count(*) filter (where classification = 'suspected_scale_error') as integer)
            as n_excluded_scale_error,
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
            count(*) filter (where classification = 'material' and explained_by is null)
            as integer
        ) as n_material_unexplained,
        count(*) filter (where classification = 'material' and explained_by is null) * 100.0
        / nullif(count(*) filter (where classification = 'material'), 0)
            as pct_material_unexplained,
        cast(count(*) filter (where classification = 'material' and flatters_trend) as integer)
            as n_material_flattering,
        count(*) filter (where classification = 'material' and flatters_trend) * 100.0
        / nullif(count(*) filter (where classification = 'material'), 0)
            as pct_material_flattering,
        cast(count(*) filter (where red_flag) as integer) as n_red_flags,
        cast(count(*) filter (where red_flag_strict) as integer) as n_red_flags_strict,
        cast(count(distinct isin) filter (where is_compared) as integer) as n_companies,
        cast(count(distinct isin) filter (where classification = 'material') as integer)
            as n_companies_with_material,
        count(distinct isin) filter (where classification = 'material') * 100.0
        / nullif(count(distinct isin) filter (where is_compared), 0)
            as pct_companies_with_material
    from pairs
    where {{ block.where }}
    {% if block.grouped %}group by {{ block.key }}{% endif %}
{% endfor %}
