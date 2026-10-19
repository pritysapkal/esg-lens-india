-- PUBLIC view of the restatement tracker: classifications, counts and percentages only, at the
-- same levels as rpt_restatement_summary (overall, metric, peer group, company, KPMG-comparable).
-- No original or restated value and no text from a filing is in this table.
-- Policy: docs/publication_policy.md.
--
-- The 5-company rule of every public group statistic: at a GROUP level (overall, metric, peer
-- group, KPMG-comparable) the shares (pct_*) are empty when fewer than 5 companies stand behind
-- the row, and suppressed_reason says so; the counts stay, as in rpt_public_group_metrics. The
-- company level is one company's own figures (n_companies = 1 by definition), not a group
-- statistic, so the rule does not apply there.
-- assert_public_models_safe checks this on every build.

with summary as (
    select
        *,
        level != 'company' and n_companies < 5 as is_small_group  -- noqa: RF04
    from {{ ref('rpt_restatement_summary') }}
)

select
    level,  -- noqa: RF04
    group_key,
    n_pairs,
    n_excluded_circular,
    n_excluded_scale_error,
    n_no_change,
    n_minor,
    n_material,
    n_unit_inconsistency,
    n_from_to_zero,
    case when not is_small_group then pct_no_change end as pct_no_change,
    case when not is_small_group then pct_minor end as pct_minor,
    case when not is_small_group then pct_material end as pct_material,
    n_material_unexplained,
    case
        when not is_small_group then pct_material_unexplained
    end as pct_material_unexplained,
    n_material_flattering,
    case
        when not is_small_group then pct_material_flattering
    end as pct_material_flattering,
    n_red_flags,
    n_red_flags_strict,
    n_companies,
    n_companies_with_material,
    case
        when not is_small_group then pct_companies_with_material
    end as pct_companies_with_material,
    case when is_small_group then 'fewer_than_5_companies' end as suppressed_reason
from summary
