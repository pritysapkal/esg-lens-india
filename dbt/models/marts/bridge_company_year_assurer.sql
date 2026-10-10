-- Which assurer(s) assessed or assured each company-year (many-to-many). assurance_type is the
-- scope filed for the BRSR Core (All / Partial); it is only filed from FY2024-25.

with assurers as (
    select distinct
        isin,
        fiscal_year_label,
        assurer_key
    from {{ ref('int_company_year_assurers') }}
),

assurance_type as (
    select
        isin,
        fiscal_year_label,
        max(coalesce(value_text, raw_value)) as assurance_type
    from {{ ref('int_metric_values') }}
    where
        metric_id = 'brsr_core_assurance_type'
        and period_role = 'CY'
        and is_latest_filing_for_value
    group by isin, fiscal_year_label
)

select
    assurers.isin,
    assurers.fiscal_year_label,
    assurers.assurer_key,
    assurance_type.assurance_type
from assurers
left join assurance_type
    on
        assurers.isin = assurance_type.isin
        and assurers.fiscal_year_label = assurance_type.fiscal_year_label
