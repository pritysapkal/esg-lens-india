-- The four parts of the Disclosure Quality Score, one row per company and financial year. Each
-- part is a rate between 0 and 1, or empty when it cannot be tested; the counts behind it are kept
-- next to it. The score measures how well a company DISCLOSES, not how well it performs.
--   completeness         = required metrics filed / required metrics. Required = mandatory from
--                          that year (metric_disclosure_requirement) and present in the taxonomy
--                          of the filing. A filed "NA" counts as disclosed; a missing or nil fact
--                          does not.
--   internal_consistency = 1 - failed checks / applicable checks, inside one filing: waste
--                          balance gap above 20%, waste recovery above 100%, implausible zeros
--                          (int_kpi_flags), and a unit or scale we had to correct. A filed
--                          intensity on another denominator is NOT a failed check.
--   temporal_consistency = 1 - flagged metrics / comparable metrics, against the next report:
--                          suspected scale error (or power-of-ten unit slip), material
--                          restatement not explained by a merger / demerger or boundary change,
--                          unexplained year-on-year jump. Empty when no later filing exists (the
--                          latest year). Scale errors count here only.
--   assurance            = points for the highest assurance level the filing marks on any
--                          disclosure (seed dqs_assurance_points). Empty before FY2023-24: no BRSR
--                          Core, no assurance field.
-- Method: docs/disclosure_quality_score.md. These counts stay local; the public model shows the
-- scores only.

{% set waste_balance_tolerance_pct = 20 %}
{% set zero_flags = {
    'wage_share': 'implausible_zero_female_wage_share',
    'energy': 'implausible_zero_energy_total',
    'water': 'implausible_zero_water_withdrawal',
    'headcount': 'implausible_zero_headcount',
} %}
{% set unit_flags = [
    'turnover_scale_corrected', 'manual_override', 'unit_conflict_text_vs_bridge',
] %}

with company_year as (
    select
        company_year.isin,
        company_year.fiscal_year_label,
        company_year.filing_id,
        company_year.symbol,
        company_year.display_name,
        company_year.peer_group,
        company_year.sector_group,
        company_year.ranking_group,
        company_year.taxonomy_version,
        coalesce(fiscal_year.is_brsr_core_year, false) as is_brsr_core_year
    from {{ ref('dim_company_year') }} as company_year
    left join {{ ref('dim_fiscal_year') }} as fiscal_year
        on company_year.fiscal_year_label = fiscal_year.fiscal_year_label
),

current_values as (
    select
        filing_id,
        metric_id,
        normalisation_flag,
        coalesce(is_nil, false) as is_nil
    from {{ ref('int_metric_values') }}
    where period_role = 'CY'
),

-- 1. completeness
taxonomy_metrics as (
    select distinct
        taxonomy_version,
        metric_id
    from {{ ref('concept_metric_map') }}
),

disclosed as (
    select distinct
        filing_id,
        metric_id
    from current_values
    where not is_nil
),

required as (
    select
        company_year.isin,
        company_year.fiscal_year_label,
        requirement.metric_id,
        disclosed.metric_id is not null as is_disclosed
    from company_year
    inner join {{ ref('metric_disclosure_requirement') }} as requirement
        on company_year.fiscal_year_label >= requirement.mandatory_from_fy
    inner join taxonomy_metrics
        on
            company_year.taxonomy_version = taxonomy_metrics.taxonomy_version
            and requirement.metric_id = taxonomy_metrics.metric_id
    left join disclosed
        on
            company_year.filing_id = disclosed.filing_id
            and requirement.metric_id = disclosed.metric_id
),

completeness as (
    select
        isin,
        fiscal_year_label,
        count(*) as n_required_metrics,
        count(*) filter (where is_disclosed) as n_disclosed_metrics,
        string_agg(metric_id, '|' order by metric_id) filter (where not is_disclosed)
            as missing_metrics
    from required
    group by isin, fiscal_year_label
),

-- 2. internal consistency
kpi_flags as (
    select
        isin,
        fiscal_year_label,
        {%- for name, flag in zero_flags.items() %}
            bool_or(flag = '{{ flag }}') as zero_{{ name }},
        {%- endfor %}
        bool_or(flag = 'waste_recovery_over_100') as waste_recovery_over_100
    from {{ ref('int_kpi_flags') }}
    group by isin, fiscal_year_label
),

unit_corrections as (
    select distinct filing_id
    from current_values
    where
        {% for flag in unit_flags -%}
            contains(normalisation_flag, '{{ flag }}'){% if not loop.last %} or {% endif %}
        {% endfor %}
),

checks as (
    select
        kpis.isin,
        kpis.fiscal_year_label,
        kpis.waste_balance_gap_pct is not null as waste_balance_applies,
        coalesce(abs(kpis.waste_balance_gap_pct) > {{ waste_balance_tolerance_pct }}, false)
            as waste_balance_fails,
        kpis.waste_recovery_rate_pct is not null as waste_recovery_applies,
        coalesce(kpi_flags.waste_recovery_over_100, false) as waste_recovery_fails,
        -- an implausible zero was set to empty in fct_company_year, so the flag itself also
        -- says that the check applied
        coalesce(kpi_flags.zero_wage_share, false) as zero_wage_share_fails,
        coalesce(kpi_flags.zero_wage_share, false)
        or (kpis.female_wage_share_pct is not null and kpis.headcount_female > 0)
            as zero_wage_share_applies,
        coalesce(kpi_flags.zero_energy, false) as zero_energy_fails,
        coalesce(kpi_flags.zero_energy, false)
        or (
            kpis.energy_total_gj is not null
            and kpis.turnover_cr > 0
            and kpis.sector_group != 'Financials'
        ) as zero_energy_applies,
        coalesce(kpi_flags.zero_water, false) as zero_water_fails,
        coalesce(kpi_flags.zero_water, false)
        or (kpis.water_withdrawal_kl is not null and kpis.sector_group != 'Financials')
            as zero_water_applies,
        coalesce(kpi_flags.zero_headcount, false) as zero_headcount_fails,
        coalesce(kpi_flags.zero_headcount, false) or kpis.headcount_total is not null
            as zero_headcount_applies,
        unit_corrections.filing_id is not null as unit_fails
    from {{ ref('fct_company_year') }} as kpis
    left join kpi_flags
        on kpis.isin = kpi_flags.isin and kpis.fiscal_year_label = kpi_flags.fiscal_year_label
    left join unit_corrections on kpis.filing_id = unit_corrections.filing_id
),

internal as (
    select
        isin,
        fiscal_year_label,
        -- the unit check applies to every filing
        1
        + cast(waste_balance_applies as integer)
        + cast(waste_recovery_applies as integer)
        {%- for name in zero_flags %}
            + cast(coalesce(zero_{{ name }}_applies, false) as integer)
        {%- endfor %}
            as n_applicable_checks,
        cast(waste_balance_fails as integer) as n_failed_waste_balance_gap,
        cast(waste_recovery_fails as integer) as n_failed_waste_recovery_over_100,
        {% for name in zero_flags -%}
            cast(zero_{{ name }}_fails as integer){% if not loop.last %} + {% endif %}
        {%- endfor %}
            as n_failed_implausible_zero,
        cast(unit_fails as integer) as n_failed_unit_inconsistency
    from checks
),

-- 3. temporal consistency
restatement_pairs as (
    select
        isin,
        value_fiscal_year_label as fiscal_year_label,
        metric_id,
        bool_or(classification in ('suspected_scale_error', 'unit_inconsistency'))
            as has_scale_error,
        bool_or(
            classification = 'material'
            and coalesce(explained_by, '') not in ('merger/demerger', 'boundary change')
        ) as has_material_restatement
    from {{ ref('fct_restatement') }}
    -- a unit taken from the restating filing makes the pair circular: nothing to compare
    where classification != 'unit_inferred_from_restating_filing'
    group by isin, value_fiscal_year_label, metric_id
),

yoy_anomalies as (
    select distinct
        isin,
        fiscal_year_label,
        case metric when 'total_headcount' then 'headcount' else metric end as metric_id
    from {{ ref('int_yoy_anomalies') }}
    where explained_by is null
),

metric_tests as (
    select
        isin,
        fiscal_year_label,
        metric_id,
        bool_or(is_pair) as is_pair,
        bool_or(has_scale_error) as has_scale_error,
        bool_or(has_material_restatement) as has_material_restatement,
        bool_or(has_yoy_anomaly) as has_yoy_anomaly
    from (
        select
            isin,
            fiscal_year_label,
            metric_id,
            true as is_pair,
            has_scale_error,
            has_material_restatement,
            false as has_yoy_anomaly
        from restatement_pairs
        union all
        select
            isin,
            fiscal_year_label,
            metric_id,
            false as is_pair,
            false as has_scale_error,
            false as has_material_restatement,
            true as has_yoy_anomaly
        from yoy_anomalies
    ) as tests
    group by isin, fiscal_year_label, metric_id
),

temporal as (
    -- each flagged metric is counted once, under the first reason that applies
    select
        isin,
        fiscal_year_label,
        count(*) filter (where is_pair) as n_paired_metrics,
        count(*) as n_comparable_metrics,
        count(*) filter (where has_scale_error) as n_metrics_scale_error,
        count(*) filter (where has_material_restatement and not has_scale_error)
            as n_metrics_material_restatement,
        count(*) filter (
            where has_yoy_anomaly and not has_scale_error and not has_material_restatement
        ) as n_metrics_yoy_anomaly
    from metric_tests
    group by isin, fiscal_year_label
),

-- 4. assurance
assurance_marks as (
    select
        filing_id,
        count(*) filter (where lower(raw_value) = 'reasonable') as n_disclosures_reasonable,
        count(*) filter (where lower(raw_value) = 'limited') as n_disclosures_limited
    from {{ ref('stg_facts') }}
    where concept like 'AssuranceSubTypeFor%'
    group by filing_id
),

assurance as (
    select
        company_year.isin,
        company_year.fiscal_year_label,
        coalesce(assurance_marks.n_disclosures_reasonable, 0) as n_disclosures_reasonable,
        coalesce(assurance_marks.n_disclosures_limited, 0) as n_disclosures_limited,
        case
            when not company_year.is_brsr_core_year then null
            when assurance_marks.n_disclosures_reasonable > 0 then 'reasonable'
            when assurance_marks.n_disclosures_limited > 0 then 'limited'
            else 'not_disclosed'
        end as assurance_level
    from company_year
    left join assurance_marks on company_year.filing_id = assurance_marks.filing_id
)

select
    company_year.isin,
    company_year.fiscal_year_label,
    company_year.symbol,
    company_year.display_name,
    company_year.peer_group,
    company_year.sector_group,
    company_year.ranking_group,
    cast(completeness.n_disclosed_metrics as double) / nullif(completeness.n_required_metrics, 0)
        as completeness,
    1 - cast(
        internal.n_failed_waste_balance_gap + internal.n_failed_waste_recovery_over_100
        + internal.n_failed_implausible_zero + internal.n_failed_unit_inconsistency as double
    ) / internal.n_applicable_checks as internal_consistency,
    case
        when temporal.n_paired_metrics > 0
            then
                1 - cast(
                    temporal.n_metrics_scale_error + temporal.n_metrics_material_restatement
                    + temporal.n_metrics_yoy_anomaly as double
                ) / temporal.n_comparable_metrics
    end as temporal_consistency,
    cast(assurance_points.points as double) as assurance,
    cast(completeness.n_required_metrics as integer) as n_required_metrics,
    cast(completeness.n_disclosed_metrics as integer) as n_disclosed_metrics,
    completeness.missing_metrics,
    cast(internal.n_applicable_checks as integer) as n_applicable_checks,
    cast(internal.n_failed_waste_balance_gap as integer) as n_failed_waste_balance_gap,
    cast(internal.n_failed_waste_recovery_over_100 as integer)
        as n_failed_waste_recovery_over_100,
    cast(internal.n_failed_implausible_zero as integer) as n_failed_implausible_zero,
    cast(internal.n_failed_unit_inconsistency as integer) as n_failed_unit_inconsistency,
    cast(
        case when temporal.n_paired_metrics > 0 then temporal.n_comparable_metrics end as integer
    ) as n_comparable_metrics,
    cast(
        case when temporal.n_paired_metrics > 0 then temporal.n_metrics_scale_error end as integer
    ) as n_metrics_scale_error,
    cast(
        case when temporal.n_paired_metrics > 0 then temporal.n_metrics_material_restatement end
        as integer
    ) as n_metrics_material_restatement,
    cast(
        case when temporal.n_paired_metrics > 0 then temporal.n_metrics_yoy_anomaly end as integer
    ) as n_metrics_yoy_anomaly,
    assurance.assurance_level,
    cast(assurance.n_disclosures_reasonable as integer) as n_disclosures_reasonable,
    cast(assurance.n_disclosures_limited as integer) as n_disclosures_limited
from company_year
left join completeness
    on
        company_year.isin = completeness.isin
        and company_year.fiscal_year_label = completeness.fiscal_year_label
left join internal
    on
        company_year.isin = internal.isin
        and company_year.fiscal_year_label = internal.fiscal_year_label
left join temporal
    on
        company_year.isin = temporal.isin
        and company_year.fiscal_year_label = temporal.fiscal_year_label
left join assurance
    on
        company_year.isin = assurance.isin
        and company_year.fiscal_year_label = assurance.fiscal_year_label
left join {{ ref('dqs_assurance_points') }} as assurance_points
    on assurance.assurance_level = assurance_points.assurance_level
