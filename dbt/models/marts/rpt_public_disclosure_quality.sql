-- PUBLIC view of the Disclosure Quality Score: the total, the component scores, the grade,
-- the rank and percentile within the ranking group and the reason codes, with names and groups.
-- All of it is calculated by us. The counts behind the components (how many metrics, which ones
-- are missing) stay local in int_dqs_components.
-- The score measures disclosure quality; it is not an ESG rating and not investment advice.
-- Policy: docs/publication_policy.md. The numeric columns must be the public_safe rows of the
-- kpi_catalogue seed for fct_disclosure_quality; assert_public_models_safe checks it on every
-- build.

select
    isin,
    symbol,
    display_name,
    fiscal_year_label,
    peer_group,
    sector_group,
    ranking_group,
    dqs_total,
    dqs_grade,
    dqs_completeness,
    dqs_mandatory_completeness,
    dqs_voluntary_depth,
    dqs_internal_consistency,
    dqs_temporal_consistency,
    dqs_assurance,
    dqs_components_used,
    is_provisional,
    assurance_level,
    assurance_scope,
    dqs_group_n,
    dqs_rank_in_group,
    dqs_percentile_in_group,
    dqs_reason_codes
from {{ ref('fct_disclosure_quality') }}
