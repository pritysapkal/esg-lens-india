-- Disclosure Quality Score (DQS) v2: one row per company and financial year. It measures how
-- complete, consistent and assured a company's DISCLOSURE is - not its ESG performance.
--   dqs_total = weighted average of the components that could be scored, weights (seed
--               dqs_weights) re-normalised over those components, x 100, one decimal. Empty when
--               fewer than two components could be scored.
--   dqs_grade = A from 85, B from 70, C from 55, D below 55 - only when at least three components
--               could be scored, else "insufficient_data" (the total is still shown).
--   rank and percentile are within the ranking group AND the financial year, only for scores
--   with at least three components and only when at least 5 companies of the group have such a
--   score that year (rank 1 and percentile 100 = best; ties share the better rank).
--   is_provisional = the temporal check could not be run because no later filing exists yet
--               (always the case for the latest year); the score can still fall.
--   dqs_reason_codes = up to three reasons, largest loss of points first, joined with "|".
-- Compare scores only within a financial year: the years are built from different components.
-- Every column is a value we calculate, so the whole table is public-safe; the counts behind the
-- components stay in int_dqs_components. Method: docs/disclosure_quality_score.md.

{% set min_components_for_grade = 3 %}
{% set reasons = {
    'missing_required_metrics':
        'w_completeness * (1 - mandatory_completeness) / n_completeness_halves',
    'low_voluntary_disclosure': 'w_completeness * (1 - voluntary_depth) / n_completeness_halves',
    'waste_balance_gap': 'w_internal * n_failed_waste_balance_gap / n_applicable_checks',
    'waste_recovery_over_100':
        'w_internal * n_failed_waste_recovery_over_100 / n_applicable_checks',
    'implausible_zero': 'w_internal * n_failed_implausible_zero / n_applicable_checks',
    'unit_inconsistency': 'w_internal * n_failed_unit_inconsistency / n_applicable_checks',
    'suspected_scale_error': 'w_temporal * n_metrics_scale_error / n_comparable_metrics',
    'material_restatement':
        'w_temporal * n_metrics_material_restatement / n_comparable_metrics',
    'unexplained_yoy_anomaly': 'w_temporal * n_metrics_yoy_anomaly / n_comparable_metrics',
    'assurance_core_only':
        "case when assurance_level = 'reasonable' then w_assurance * (1 - assurance) end",
    'assessment_not_assurance':
        "case when assurance_level = 'assessment' then w_assurance * (1 - assurance) end",
    'limited_assurance':
        "case when assurance_level = 'limited' then w_assurance * (1 - assurance) end",
    'no_assurance':
        "case when assurance_level in ('none', 'not_disclosed') "
        ~ "then w_assurance * (1 - assurance) end",
} %}

with weights as (
    select
        max(weight) filter (where component = 'completeness') as w_completeness,
        max(weight) filter (where component = 'internal_consistency') as w_internal,
        max(weight) filter (where component = 'temporal_consistency') as w_temporal,
        max(weight) filter (where component = 'assurance') as w_assurance
    from {{ ref('dqs_weights') }}
),

components as (
    select
        components.*,
        weights.*
    from {{ ref('int_dqs_components') }} as components
    cross join weights
),

scored as (
    select
        *,
        round(
            {{ dqs_weighted_total('w_completeness', 'w_internal', 'w_temporal', 'w_assurance') }},
            1
        ) as dqs_total,
        cast(completeness is not null as integer)
        + cast(internal_consistency is not null as integer)
        + cast(temporal_consistency is not null as integer)
        + cast(assurance is not null as integer) as dqs_components_used,
        cast(mandatory_completeness is not null as integer)
        + cast(voluntary_depth is not null as integer) as n_completeness_halves
    from components
),

-- points of weight lost per reason; the re-normalisation divides every reason of a company-year
-- by the same number, so it does not change their order
lost_points as (
    {% for reason, lost in reasons.items() %}
        select
            isin,
            fiscal_year_label,
            '{{ reason }}' as reason,
            {{ loop.index }} as reason_order,
            {{ lost }} as lost
        from scored
        {% if not loop.last %}union all{% endif %}
    {% endfor %}
),

ranked_reasons as (
    select
        *,
        row_number() over (
            partition by isin, fiscal_year_label
            order by lost desc, reason_order asc
        ) as reason_rank
    from lost_points
    where lost > 0
),

reason_codes as (
    select
        isin,
        fiscal_year_label,
        string_agg(reason, '|' order by reason_rank) as dqs_reason_codes
    from ranked_reasons
    where reason_rank <= 3
    group by isin, fiscal_year_label
),

rankable as (
    select
        *,
        case
            when dqs_components_used >= {{ min_components_for_grade }} then dqs_total
        end as rank_score
    from scored
),

ranked as (
    select
        *,
        count(rank_score) over (partition by ranking_group, fiscal_year_label) as group_n,
        rank() over (
            partition by ranking_group, fiscal_year_label, rank_score is null
            order by rank_score desc
        ) as group_rank,
        percent_rank() over (
            partition by ranking_group, fiscal_year_label, rank_score is null
            order by rank_score asc
        ) as rank_fraction
    from rankable
)

select
    ranked.isin,
    ranked.fiscal_year_label,
    ranked.symbol,
    ranked.display_name,
    ranked.peer_group,
    ranked.sector_group,
    ranked.ranking_group,
    cast(ranked.dqs_total as double) as dqs_total,
    case
        when ranked.rank_score is null then 'insufficient_data'
        when ranked.rank_score >= 85 then 'A'
        when ranked.rank_score >= 70 then 'B'
        when ranked.rank_score >= 55 then 'C'
        else 'D'
    end as dqs_grade,
    cast(ranked.completeness as double) as dqs_completeness,
    cast(ranked.mandatory_completeness as double) as dqs_mandatory_completeness,
    cast(ranked.voluntary_depth as double) as dqs_voluntary_depth,
    cast(ranked.internal_consistency as double) as dqs_internal_consistency,
    cast(ranked.temporal_consistency as double) as dqs_temporal_consistency,
    cast(ranked.assurance as double) as dqs_assurance,
    cast(ranked.dqs_components_used as integer) as dqs_components_used,
    ranked.temporal_consistency is null as is_provisional,
    ranked.assurance_level,
    ranked.assurance_scope,
    cast(ranked.group_n as integer) as dqs_group_n,
    cast(
        case
            when
                ranked.rank_score is not null
                and ranked.ranking_group is not null
                and ranked.group_n >= 5
                then ranked.group_rank
        end as integer
    ) as dqs_rank_in_group,
    cast(
        case
            when
                ranked.rank_score is not null
                and ranked.ranking_group is not null
                and ranked.group_n >= 5
                then round(ranked.rank_fraction * 100, 1)
        end as double
    ) as dqs_percentile_in_group,
    reason_codes.dqs_reason_codes
from ranked
left join reason_codes
    on ranked.isin = reason_codes.isin and ranked.fiscal_year_label = reason_codes.fiscal_year_label
