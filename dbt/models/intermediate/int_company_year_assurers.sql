-- One row per assurance / assessment provider named in a filing (several per filing possible),
-- with spelling variants merged. Names come from the facts
-- NameOfTheCompanyOrLLPOrFirmOf(Assessment)OrAssuranceProvider
-- (FY2023-24 uses the "Assurance" concept, FY2024-25 onwards "AssessmentOrAssurance").
-- Merging: the name is lower-cased and stripped of accents and punctuation; the first matching
-- pattern of the assurer_aliases seed gives the canonical name, otherwise the cleaned name is kept.

with provider_rows as (
    select
        filing_id,
        isin,
        fiscal_year_label,
        dimension_key,
        max(
            case
                when concept like 'NameOfTheCompanyOrLLPOrFirmOf%AssuranceProvider' then raw_value
            end
        ) as name_filed,
        max(
            case
                when concept like 'CompanyIDOrLLPIDOrFirmIDOf%AssuranceProvider' then raw_value
            end
        ) as id_filed
    from {{ ref('int_facts_with_context') }}
    where
        concept like 'NameOfTheCompanyOrLLPOrFirmOf%AssuranceProvider'
        or concept like 'CompanyIDOrLLPIDOrFirmIDOf%AssuranceProvider'
    group by filing_id, isin, fiscal_year_label, dimension_key
),

keyed as (
    select
        *,
        trim(
            regexp_replace(
                regexp_replace(lower(strip_accents(name_filed)), '&', ' and ', 'g'),
                '[^a-z0-9]+', ' ', 'g'
            )
        ) as name_key,
        trim(
            regexp_replace(
                regexp_replace(
                    regexp_replace(name_filed, '\s*\([^)]*\)', '', 'g'),
                    '(?i)^(m/s\.?|messrs\.?|for)\s+', ''
                ),
                '[\s,.]+$', ''
            )
        ) as name_cleaned
    from provider_rows
    where coalesce(trim(name_filed), '') != ''
),

aliased as (
    select
        keyed.*,
        aliases.assurer_name as alias_name,
        row_number() over (
            partition by keyed.filing_id, keyed.dimension_key
            order by aliases.priority, length(aliases.pattern) desc
        ) as rn
    from keyed
    left join {{ ref('assurer_aliases') }} as aliases
        on contains(keyed.name_key, aliases.pattern)
),

resolved as (
    select
        filing_id,
        isin,
        fiscal_year_label,
        name_filed,
        upper(regexp_replace(coalesce(id_filed, ''), '[\s.]', '', 'g')) as id_clean,
        coalesce(alias_name, name_cleaned) as assurer_name
    from aliased
    where rn = 1
),

named as (
    select
        *,
        trim(both '_' from lower(regexp_replace(assurer_name, '[^a-zA-Z0-9]+', '_', 'g')))
            as assurer_key
    from resolved
)

select * from named
