-- Every catalogue metric value of every filing: current-year values and the prior-year
-- comparatives filed a year (or two) later. Grain: company x metric x year the value belongs to
-- x breakdown x source filing. Only the newest revision of a company-year is "latest".
-- is_latest_value = the CY value from the latest revision of the company's filing for that
-- year; PY / PY2 comparatives are kept but never latest. Values with period role OTHER (periods
-- that fit no reporting year) are left out. When one filing holds several facts for the same
-- grain (a company filing the comparative twice), the one with the latest period end is kept
-- and n_competing_values says how many there were.
-- best_value_std is the value gold KPIs use: value_std, except where the official current
-- value is a suspected scale error against the comparative in the next report (more than 100x
-- apart, int_scale_error_suspects) - then the later comparative replaces it and
-- best_value_source says so. value_std always keeps what was filed.
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
),

suspects as (
    select
        isin,
        metric_id,
        dimension_key,
        value_fiscal_year_label,
        restated_value
    from {{ ref('int_scale_error_suspects') }}
),

joined as (
    select
        metric_values.*,
        filings.filed_date,
        filings.submission_date,
        filings.has_revision_date,
        filings.is_latest_revision,
        names.company_name_clean,
        suspects.restated_value as later_comparative,
        metric_values.period_role = 'CY' and filings.is_latest_revision as is_latest_value
    from metric_values
    inner join filings on metric_values.filing_id = filings.filing_id
    left join names on metric_values.filing_id = names.filing_id
    left join suspects
        on
            metric_values.isin = suspects.isin
            and metric_values.metric_id = suspects.metric_id
            and metric_values.dimension_key = suspects.dimension_key
            and metric_values.value_fiscal_year_label = suspects.value_fiscal_year_label
    where metric_values.rn = 1
)

select
    isin,
    symbol,
    metric_id,
    value_fiscal_year_label,
    dimension_key,
    filing_id as source_filing_id,
    fiscal_year_label as filing_fiscal_year_label,
    cast(value_std as double) as value_std,
    cast(
        case
            when is_latest_value and later_comparative is not null then later_comparative
            else value_std
        end as double
    ) as best_value_std,
    case
        when is_latest_value and later_comparative is not null
            then 'replaced_by_later_comparative'
        else 'as_filed'
    end as best_value_source,
    unit_std,
    cast(value_pct as double) as value_pct,
    raw_value,
    value_text,
    period_role,
    coalesce(company_name_clean, company_name) || ', BRSR '
    || fiscal_year_label || ', filed on NSE ' || cast(filed_date as varchar)
    || case
        when has_revision_date
            then ' (revised; first filed ' || cast(submission_date as varchar) || ')'
        else ''
    end as source_citation,
    period_role = 'CY' as is_current_year_value,
    is_latest_value,
    is_latest_revision as is_latest_revision_filing,
    {{ unit_resolution_method('normalisation_flag') }} as unit_resolution_method,
    override_id,
    normalisation_flag,
    is_material,
    cast(n_competing_values as integer) as n_competing_values
from joined
