-- One row per parsed filing: typed main reporting period, fiscal-year label and size counts,
-- enriched with the identifier details from the intake manifest and the label from the listing.

with filings as (
    select * from {{ source('brsr_raw', 'filings') }}
),

manifest as (
    select
        filing_id,
        isin_source,
        entity_identifier,
        entity_identifier_scheme
    from {{ source('intake', 'manifest') }}
),

listing as (
    select
        filing_id,
        reporting_year_label
    from {{ source('intake', 'listing') }}
),

typed as (
    select
        filings.filing_id,
        filings.symbol,
        filings.isin,
        manifest.isin_source,
        manifest.entity_identifier,
        manifest.entity_identifier_scheme,
        filings.taxonomy_version,
        filings.file_path,
        filings.main_context_id,
        cast(filings.period_start as date) as period_start,
        cast(filings.period_end as date) as period_end,
        cast(filings.period_days as integer) as period_days,
        cast(filings.period_months as integer) as period_months,
        filings.is_non_standard_period,
        coalesce(listing.reporting_year_label, filings.reporting_year_label)
            as reporting_year_label,
        cast(filings.n_facts as integer) as n_facts,
        cast(filings.n_numeric as integer) as n_numeric,
        cast(filings.n_text as integer) as n_text,
        cast(filings.n_nil as integer) as n_nil,
        cast(filings.n_concepts as integer) as n_concepts,
        cast(filings.n_contexts as integer) as n_contexts,
        cast(filings.n_units as integer) as n_units,
        cast(filings.n_dimension_axes as integer) as n_dimension_axes,
        filings.parse_seconds,
        filings.parser_version
    from filings
    left join manifest on filings.filing_id = manifest.filing_id
    left join listing on filings.filing_id = listing.filing_id
)

select
    *,
    {{ fiscal_year_label('period_end') }} as fiscal_year_label,
    coalesce(
        reporting_year_label
        = cast({{ fiscal_year_start('period_end') }} as varchar)
        || '-'
        || cast({{ fiscal_year_start('period_end') }} + 1 as varchar),
        false
    ) as label_matches_period
from typed
