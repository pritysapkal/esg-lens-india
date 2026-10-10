-- PUBLIC view of the restatement tracker: classifications, counts and percentages only, at the
-- same levels as rpt_restatement_summary (overall, metric, peer group, company, KPMG-comparable).
-- No original or restated value and no text from a filing is in this table.
-- Policy: docs/publication_policy.md.

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
    pct_no_change,
    pct_minor,
    pct_material,
    n_material_unexplained,
    pct_material_unexplained,
    n_material_flattering,
    pct_material_flattering,
    n_red_flags,
    n_red_flags_strict,
    n_companies,
    n_companies_with_material,
    pct_companies_with_material
from {{ ref('rpt_restatement_summary') }}
