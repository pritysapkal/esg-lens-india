-- Sensitivity of the Disclosure Quality Score to its weights: the ranking of all companies in a
-- year with the blueprint weights (seed dqs_weights) against equal weights (0.25 each), both with
-- the same re-weighting over the components that could be scored.
--   spearman_rank_correlation   correlation of the two rankings (average ranks for ties)
--   n_moving_5_or_more_ranks    companies whose rank changes by 5 places or more
-- Run:  dbt show --select dqs_weight_sensitivity --profiles-dir .
-- Results are written up in docs/disclosure_quality_score.md.

with weights as (
    select
        max(weight) filter (where component = 'completeness') as w_completeness,
        max(weight) filter (where component = 'internal_consistency') as w_internal,
        max(weight) filter (where component = 'temporal_consistency') as w_temporal,
        max(weight) filter (where component = 'assurance') as w_assurance
    from {{ ref('dqs_weights') }}
),

scores as (
    select
        components.isin,
        components.fiscal_year_label,
        {{ dqs_weighted_total('w_completeness', 'w_internal', 'w_temporal', 'w_assurance') }}
            as dqs_blueprint,
        {{ dqs_weighted_total(0.25, 0.25, 0.25, 0.25) }} as dqs_equal
    from {{ ref('int_dqs_components') }} as components
    cross join weights
),

ranks as (
    select
        *,
        rank() over (partition by fiscal_year_label order by dqs_blueprint desc)
            as rank_blueprint,
        rank() over (partition by fiscal_year_label order by dqs_equal desc) as rank_equal,
        count(*) over (partition by fiscal_year_label, dqs_blueprint) as ties_blueprint,
        count(*) over (partition by fiscal_year_label, dqs_equal) as ties_equal
    from scores
    where dqs_blueprint is not null
),

average_ranks as (
    select
        *,
        rank_blueprint + (ties_blueprint - 1) / 2.0 as average_rank_blueprint,
        rank_equal + (ties_equal - 1) / 2.0 as average_rank_equal,
        abs(rank_blueprint - rank_equal) as rank_move
    from ranks
),

-- every company-year twice: under its own year and under 'all years'
scoped as (
    select
        *,
        fiscal_year_label as scope
    from average_ranks
    union all
    select
        *,
        'all years' as scope
    from average_ranks
)

select
    scope as fiscal_year_label,
    count(*) as n_company_years,
    round(corr(average_rank_blueprint, average_rank_equal), 3) as spearman_rank_correlation,
    count(*) filter (where rank_move >= 5) as n_moving_5_or_more_ranks,
    max(rank_move) as largest_rank_move,
    round(avg(abs(dqs_blueprint - dqs_equal)), 1) as mean_abs_score_difference
from scoped
group by scope
order by scope
