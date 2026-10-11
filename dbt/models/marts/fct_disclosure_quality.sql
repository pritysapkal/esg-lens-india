-- Disclosure Quality Score (DQS): one row per company and financial year. It measures how
-- complete, consistent and assured a company's DISCLOSURE is - not its ESG performance.
--   dqs_total = weighted average of the components that could be scored, weights (seed
--               dqs_weights) re-normalised over those components, x 100, one decimal. Empty when
--               fewer than two components could be scored.
--   dqs_grade = A from 85, B from 70, C from 55, D below 55.
--   rank and percentile are within the ranking group and year, only when at least 5 companies
--   there have a score (rank 1 and percentile 100 = best; ties share the better rank).
--   dqs_reason_codes = up to three reasons, largest loss of points first, joined with "|".
-- Every column is a value we calculate, so the whole table is public-safe; the counts behind the
-- components stay in int_dqs_components. Method: docs/disclosure_quality_score.md.

{% set reasons = {
    'missing_required_metrics': 'w_completeness * (1 - completeness)',
    'waste_balance_gap': 'w_internal * n_failed_waste_balance_gap / n_applicable_checks',
    'waste_recovery_over_100':
        'w_internal * n_failed_waste_recovery_over_100 / n_applicable_checks',
    'implausible_zero': 'w_internal * n_failed_implausible_zero / n_applicable_checks',
    'unit_inconsistency': 'w_internal * n_failed_unit_inconsistency / n_applicable_checks',
    'suspected_scale_error': 'w_temporal * n_metrics_scale_error / n_comparable_metrics',
    'material_restatement':
        'w_temporal * n_metrics_material_restatement / n_comparable_metrics',
    'unexplained_yoy_anomaly': 'w_temporal * n_metrics_yoy_anomaly / n_comparable_metrics',
    'limited_assurance':
        "case when assurance_level = 'limited' then w_assurance * (1 - assurance) end",
    'no_assurance':
        "case when assurance_level != 'limited' then w_assurance * (1 - assurance) end",
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
        + cast(assurance is not null as integer) as dqs_components_used
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

ranked as (
    select
        *,
        count(dqs_total) over (partition by ranking_group, fiscal_year_label) as group_n,
        rank() over (
            partition by ranking_group, fiscal_year_label, dqs_total is null
            order by dqs_total desc
        ) as group_rank,
        percent_rank() over (
            partition by ranking_group, fiscal_year_label, dqs_total is null
            order by dqs_total asc
        ) as rank_fraction
    from scored
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
        when ranked.dqs_total >= 85 then 'A'
        when ranked.dqs_total >= 70 then 'B'
        when ranked.dqs_total >= 55 then 'C'
        when ranked.dqs_total < 55 then 'D'
    end as dqs_grade,
    cast(ranked.completeness as double) as dqs_completeness,
    cast(ranked.internal_consistency as double) as dqs_internal_consistency,
    cast(ranked.temporal_consistency as double) as dqs_temporal_consistency,
    cast(ranked.assurance as double) as dqs_assurance,
    cast(ranked.dqs_components_used as integer) as dqs_components_used,
    ranked.assurance_level,
    cast(ranked.group_n as integer) as dqs_group_n,
    cast(
        case
            when
                ranked.dqs_total is not null
                and ranked.ranking_group is not null
                and ranked.group_n >= 5
                then ranked.group_rank
        end as integer
    ) as dqs_rank_in_group,
    cast(
        case
            when
                ranked.dqs_total is not null
                and ranked.ranking_group is not null
                and ranked.group_n >= 5
                then round(ranked.rank_fraction * 100, 1)
        end as double
    ) as dqs_percentile_in_group,
    reason_codes.dqs_reason_codes
from ranked
left join reason_codes
    on ranked.isin = reason_codes.isin and ranked.fiscal_year_label = reason_codes.fiscal_year_label
