-- Every catalogue metric value of every filing: current-year values and the prior-year
-- comparatives filed a year (or two) later. Grain: company x metric x year the value belongs to
-- x breakdown x source filing. Only the newest revision of a company-year is "latest".
-- is_latest_value = the CY value from the latest revision of the company's filing for that
-- year; PY / PY2 comparatives are kept but never latest. Values with period role OTHER (periods
-- that fit no reporting year) are left out. When one filing holds several facts for the same
-- grain (a company filing the comparative twice), the one with the latest period end is kept
-- and n_competing_values says how many there were.
-- Citation policy: plain text only, never a link to the exchange.

with metric_values as (
    select
        *,
        row_number() over (
            partition by isin, metric_id, value_fiscal_year_label, dimension_key, filing_id
            order by value_period_end desc nulls last, value_std is not null desc, fact_id
        ) as rn,
        count(*) over (
            partition by isin, metric_id, value_fiscal_year_label, dimension_key, filing_id
        ) as n_competing_values
    from {{ ref('int_metric_values_enriched') }}
    where period_role in ('CY', 'PY', 'PY2') and value_fiscal_year_label is not null
),

filings as (
    select * from {{ ref('int_filing_revisions') }}
),

names as (
    select
        filing_id,
        company_name_clean
    from {{ ref('int_company_names') }}
)

select
    metric_values.isin,
    metric_values.symbol,
    metric_values.metric_id,
    metric_values.value_fiscal_year_label,
    metric_values.dimension_key,
    metric_values.filing_id as source_filing_id,
    metric_values.fiscal_year_label as filing_fiscal_year_label,
    cast(metric_values.value_std as double) as value_std,
    metric_values.unit_std,
    cast(metric_values.value_pct as double) as value_pct,
    metric_values.raw_value,
    metric_values.value_text,
    metric_values.period_role,
    coalesce(names.company_name_clean, metric_values.company_name) || ', BRSR '
    || metric_values.fiscal_year_label || ', filed on NSE ' || cast(filings.filed_date as varchar)
    || case
        when filings.has_revision_date
            then ' (revised; first filed ' || cast(filings.submission_date as varchar) || ')'
        else ''
    end as source_citation,
    metric_values.period_role = 'CY' as is_current_year_value,
    metric_values.period_role = 'CY' and filings.is_latest_revision as is_latest_value,
    filings.is_latest_revision as is_latest_revision_filing,
    case
        when contains(metric_values.normalisation_flag, 'unit_bridged_from_next_filing')
            then 'bridged-from-next-filing'
        when contains(metric_values.normalisation_flag, 'unit_from_text') then 'text-unit'
        when contains(metric_values.normalisation_flag, 'unit_format_default') then 'default'
        else 'as-filed'
    end as unit_resolution_method,
    metric_values.override_id,
    metric_values.normalisation_flag,
    metric_values.is_material,
    cast(metric_values.n_competing_values as integer) as n_competing_values
from metric_values
inner join filings on metric_values.filing_id = filings.filing_id
left join names on metric_values.filing_id = names.filing_id
where metric_values.rn = 1
