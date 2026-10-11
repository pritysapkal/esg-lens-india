-- Assurance component of the Disclosure Quality Score, one row per company and financial year.
-- SEBI requires the top 150 listed companies to obtain reasonable assurance on the BRSR Core from
-- FY2023-24, so for this universe Core assurance is compliance, not quality. The component
-- therefore gives the baseline for what was obtained and the rest for going beyond it:
--   assurance_level  what the filing reports (seed dqs_assurance_points gives the points):
--     assessment     the company states a third-party "assessment" instead of assurance (allowed
--                    since SEBI's circular of 28 March 2025)
--     reasonable     at least one disclosure is marked as assured at the Reasonable level
--     limited        disclosures are marked at the Limited level only
--     not_disclosed  the filing marks nothing as assured
--   assurance_scope  all = the whole report is covered: the filed type is "All", or (FY2023-24,
--                    before that field existed) every section's type of assurance is "All";
--                    partial otherwise. "All" adds the whole-report bonus.
-- Empty for years before the BRSR Core (FY2022-23): the report had no place to state it.
-- Method: docs/disclosure_quality_score.md.

with company_year as (
    select
        company_year.isin,
        company_year.fiscal_year_label,
        company_year.filing_id,
        coalesce(fiscal_year.is_brsr_core_year, false) as is_brsr_core_year
    from {{ ref('dim_company_year') }} as company_year
    left join {{ ref('dim_fiscal_year') }} as fiscal_year
        on company_year.fiscal_year_label = fiscal_year.fiscal_year_label
),

marks as (
    select
        filing_id,
        count(*) filter (
            where concept like 'AssuranceSubTypeFor%' and lower(raw_value) = 'reasonable'
        ) as n_disclosures_reasonable,
        count(*) filter (
            where concept like 'AssuranceSubTypeFor%' and lower(raw_value) = 'limited'
        ) as n_disclosures_limited,
        count(*) filter (where concept like 'TypeOfAssuranceFor%') as n_sections,
        count(*) filter (
            where concept like 'TypeOfAssuranceFor%' and lower(raw_value) = 'all'
        ) as n_sections_all,
        max(
            case
                when concept = 'WhetherTheCompanyHasUndertakenAssessmentOrAssuranceOfTheBRSRCore'
                    then lower(raw_value)
            end
        ) as status_filed,
        max(case when concept = 'TypeOfAssessmentOrAssuranceObtain' then lower(raw_value) end)
            as type_filed
    from {{ ref('stg_facts') }}
    where
        concept like 'AssuranceSubTypeFor%'
        or concept like 'TypeOfAssuranceFor%'
        or concept in (
            'WhetherTheCompanyHasUndertakenAssessmentOrAssuranceOfTheBRSRCore',
            'TypeOfAssessmentOrAssuranceObtain'
        )
    group by filing_id
),

classified as (
    select
        company_year.isin,
        company_year.fiscal_year_label,
        company_year.is_brsr_core_year,
        coalesce(marks.n_disclosures_reasonable, 0) as n_disclosures_reasonable,
        coalesce(marks.n_disclosures_limited, 0) as n_disclosures_limited,
        coalesce(marks.n_sections, 0) as n_sections,
        coalesce(marks.n_sections_all, 0) as n_sections_all,
        case
            when not company_year.is_brsr_core_year then null
            when marks.status_filed like '%assessment%' then 'assessment'
            when marks.n_disclosures_reasonable > 0 then 'reasonable'
            when marks.n_disclosures_limited > 0 then 'limited'
            else 'not_disclosed'
        end as assurance_level,
        case
            when marks.type_filed is not null then marks.type_filed = 'all'
            else coalesce(marks.n_sections > 0 and marks.n_sections_all = marks.n_sections, false)
        end as is_whole_report
    from company_year
    left join marks on company_year.filing_id = marks.filing_id
),

points as (
    select max(points) filter (where item = 'whole_report_bonus') as whole_report_bonus
    from {{ ref('dqs_assurance_points') }}
)

select
    classified.isin,
    classified.fiscal_year_label,
    classified.assurance_level,
    case
        when classified.assurance_level is null then null
        when classified.assurance_level = 'not_disclosed' then null
        when classified.is_whole_report then 'all'
        else 'partial'
    end as assurance_scope,
    -- least() skips empty values, so the "no level" case is kept empty explicitly
    cast(
        case
            when level_points.points is not null
                then
                    least(
                        1,
                        level_points.points
                        + case
                            when classified.is_whole_report and level_points.points > 0
                                then points.whole_report_bonus
                            else 0
                        end
                    )
        end as double
    ) as assurance,
    cast(level_points.points as double) as assurance_baseline_points,
    cast(classified.n_disclosures_reasonable as integer) as n_disclosures_reasonable,
    cast(classified.n_disclosures_limited as integer) as n_disclosures_limited,
    cast(classified.n_sections as integer) as n_sections,
    cast(classified.n_sections_all as integer) as n_sections_all
from classified
cross join points
left join {{ ref('dqs_assurance_points') }} as level_points
    on classified.assurance_level = level_points.item
