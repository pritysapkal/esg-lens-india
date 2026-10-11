-- Voluntary depth, detail: one row per company-year and Leadership indicator of the taxonomy of
-- that filing, saying whether the company filed a substantive value for it.
-- Leadership indicators are voluntary in BRSR; which elements belong to which indicator comes
-- from the taxonomy itself (seed leadership_indicator_map, built from the presentation linkbase).
-- An indicator is disclosed when at least one of its elements has, for the reporting year,
--   * a number (a zero counts: it is an answer), or
--   * a text that is not empty and is not "NA", "Not applicable", "-", "Nil" or "None".
-- A yes / no answer counts. All parsed facts are used (stg_facts through int_period_role, and
-- the long texts of stg_text_facts), not only the catalogue metrics.
-- Input for the Disclosure Quality Score; method: docs/disclosure_quality_score.md.

{{ config(materialized='table') }}

{% set nothing_to_report = "'^(nil|none)\\.?$'" %}

with company_year as (
    select
        isin,
        fiscal_year_label,
        filing_id,
        taxonomy_version
    from {{ ref('dim_company_year') }}
),

indicator_concepts as (
    select
        taxonomy_version,
        principle,
        indicator,
        indicator_seq,
        concept
    from {{ ref('leadership_indicator_map') }}
),

short_facts as (
    select
        filing_id,
        concept,
        case
            when is_numeric then value_num is not null
            else
                trim(coalesce(raw_value, '')) != ''
                and not is_na_text
                and not regexp_matches(lower(trim(raw_value)), {{ nothing_to_report }})
        end as is_substantive
    from {{ ref('int_period_role') }}
    where period_role in ('CY', 'INSTANT_CY') and not is_nil
),

-- long texts may be wrapped in HTML; a comparative-year text block is not expected
long_texts as (
    select
        filing_id,
        concept,
        regexp_replace(text, '<[^>]+>|&nbsp;', ' ', 'g') as plain_text
    from {{ ref('stg_text_facts') }}
    where not is_nil
),

text_facts as (
    select
        filing_id,
        concept,
        trim(coalesce(plain_text, '')) != ''
        and not {{ is_na_text('plain_text') }}
        and not regexp_matches(lower(trim(plain_text)), {{ nothing_to_report }}) as is_substantive
    from long_texts
),

substantive_concepts as (
    select distinct
        filing_id,
        concept
    from (
        select * from short_facts
        union all
        select * from text_facts
    ) as facts
    where is_substantive
)

select
    company_year.isin,
    company_year.fiscal_year_label,
    company_year.taxonomy_version,
    indicator_concepts.principle,
    indicator_concepts.indicator,
    cast(min(indicator_concepts.indicator_seq) as integer) as indicator_seq,
    cast(count(*) as integer) as n_concepts,
    cast(count(substantive_concepts.concept) as integer) as n_concepts_with_value,
    count(substantive_concepts.concept) > 0 as is_disclosed
from company_year
inner join indicator_concepts
    on company_year.taxonomy_version = indicator_concepts.taxonomy_version
left join substantive_concepts
    on
        company_year.filing_id = substantive_concepts.filing_id
        and indicator_concepts.concept = substantive_concepts.concept
group by
    company_year.isin,
    company_year.fiscal_year_label,
    company_year.taxonomy_version,
    indicator_concepts.principle,
    indicator_concepts.indicator
