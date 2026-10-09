-- The real unit of quantities that old taxonomies (2021-09-30, 2023-06-30) file with unit 'pure'
-- (or as text), one row per filing and metric. Resolved in this order (docs/business_rules.md):
--   1. bridge_next_filing: the company's next filing reports the same year as its PY value with a
--      real unit, and that value matches this filing's CY value within 5 % -> use that unit;
--   2. text_unit: the companion text fact UnitOf<concept> (emissions only), via
--      seeds/text_unit_normalisation.csv - only if it converts to the metric's unit_std;
--   3. format_default: the BRSR format's own unit (tCO2e, GJ, kl, t, per rupee).
-- unit_conflict = the bridge and the text unit disagree on the multiplier. The text unit then
-- wins: a conflict only happens when the next filing labels the value 'MtCO2e', and for those
-- filers (e.g. NTPC: 'Million metric tonnes', 335.72) Mt meant megatonnes, not metric tonnes.

{{ config(materialized='table') }}

with facts as (
    select * from {{ ref('int_period_role') }}
),

metric_map as (
    select * from {{ ref('concept_metric_map') }}
),

units as (
    select * from {{ ref('unit_normalisation') }}
),

text_units as (
    select * from {{ ref('text_unit_normalisation') }}
),

mapped as (
    select
        facts.*,
        metric_map.metric_id,
        metric_map.unit_std
    from facts
    inner join metric_map
        on
            facts.taxonomy_version = metric_map.taxonomy_version
            and facts.concept = metric_map.concept
),

old_quantities as (
    select *
    from mapped
    where
        coalesce(unit_label, 'pure') = 'pure'
        and {{ default_unit_for('unit_std') }} is not null
        and not has_dimensions
),

targets as (
    select distinct
        filing_id,
        symbol,
        concept,
        metric_id,
        unit_std
    from old_quantities
),

bridge as (
    select
        this_filing.filing_id,
        this_filing.metric_id,
        mode(next_filing.unit_label) as bridge_unit_label,
        count(*) as n_bridge_matches
    from old_quantities as this_filing
    inner join mapped as next_filing
        on
            this_filing.symbol = next_filing.symbol
            and this_filing.metric_id = next_filing.metric_id
            and this_filing.value_period_end = next_filing.value_period_end
            and next_filing.period_role = 'PY'
            and coalesce(next_filing.unit_label, 'pure') != 'pure'
            and not next_filing.has_dimensions
    where
        this_filing.period_role = 'CY'
        and this_filing.value_num > 0
        and abs(next_filing.value_num / this_filing.value_num - 1) <= 0.05
    group by this_filing.filing_id, this_filing.metric_id
),

text_unit as (
    select
        targets.filing_id,
        targets.metric_id,
        arg_min(unit_fact.value_text, unit_fact.period_role != 'CY') as text_unit_raw
    from targets
    inner join facts as unit_fact
        on
            targets.filing_id = unit_fact.filing_id
            and unit_fact.concept = 'UnitOf' || targets.concept
            and unit_fact.value_text is not null
    group by targets.filing_id, targets.metric_id
),

resolved as (
    select
        targets.filing_id,
        targets.symbol,
        targets.metric_id,
        targets.unit_std,
        bridge.bridge_unit_label,
        bridge.n_bridge_matches,
        text_unit.text_unit_raw,
        text_units.unit_label as text_unit_label,
        {{ default_unit_for('targets.unit_std') }} as default_unit_label
    from targets
    left join bridge
        on targets.filing_id = bridge.filing_id and targets.metric_id = bridge.metric_id
    left join text_unit
        on targets.filing_id = text_unit.filing_id and targets.metric_id = text_unit.metric_id
    left join text_units
        on {{ normalise_unit_text('text_unit.text_unit_raw') }} = text_units.unit_text
),

with_conflict as (
    select
        resolved.* exclude (text_unit_label),
        -- a text unit counts only if it converts to the metric's unit (an emissions TOTAL text
        -- unit such as 'metric tonnes of CO2 equivalent' says nothing about an intensity)
        case when text_units_m.unit_label_raw is not null then resolved.text_unit_label end
            as text_unit_label,
        coalesce(bridge_units.multiplier != text_units_m.multiplier, false) as unit_conflict
    from resolved
    left join units as bridge_units
        on
            resolved.bridge_unit_label = bridge_units.unit_label_raw
            and resolved.unit_std = bridge_units.unit_std
    left join units as text_units_m
        on
            resolved.text_unit_label = text_units_m.unit_label_raw
            and resolved.unit_std = text_units_m.unit_std
)

select
    filing_id,
    symbol,
    metric_id,
    unit_std,
    case
        when unit_conflict then text_unit_label
        else coalesce(bridge_unit_label, text_unit_label, default_unit_label)
    end as implied_unit_label,
    case
        when unit_conflict then 'text_unit'
        when bridge_unit_label is not null then 'bridge_next_filing'
        when text_unit_label is not null then 'text_unit'
        else 'format_default'
    end as unit_source,
    bridge_unit_label,
    n_bridge_matches,
    text_unit_raw,
    text_unit_label,
    unit_conflict
from with_conflict
