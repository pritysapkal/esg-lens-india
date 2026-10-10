-- Suspected scale errors: the value a company filed for year Y (current-year value, latest
-- revision) against the comparative for Y in its next report (prior-year value of the Y+1 filing,
-- latest revision), where one is more than 100 times the other. That is a unit / scale mistake in
-- one of the two filings, not a restatement. Gold uses the later comparative as the "best
-- available value" for these, and the restatement tracker leaves them out of its statistics.
-- Filed intensities are not tested: companies change the denominator (per rupee, per crore)
-- between years, which is a different finding (see ghg_intensity_filed_basis).
-- Input for the Disclosure Quality Score (Week 8).

with metric_values as (
    select
        metric_values.*,
        revisions.is_latest_revision
    from {{ ref('int_metric_values') }} as metric_values
    inner join {{ ref('int_filing_revisions') }} as revisions
        on metric_values.filing_id = revisions.filing_id
    where
        metric_values.value_std is not null
        and metric_values.metric_id not like '%intensity_filed%'
        and revisions.is_latest_revision
),

originals as (
    select
        isin,
        symbol,
        metric_id,
        dimension_key,
        value_fiscal_year_label,
        max(filing_id) as original_filing_id,
        max(value_std) as original_value,
        max({{ unit_resolution_method('normalisation_flag') }}) as unit_resolution_method
    from metric_values
    where period_role = 'CY'
    group by isin, symbol, metric_id, dimension_key, value_fiscal_year_label
),

comparatives as (
    select
        isin,
        metric_id,
        dimension_key,
        value_fiscal_year_label,
        max(filing_id) as later_filing_id,
        arg_max(value_std, value_period_end) as restated_value
    from metric_values
    where period_role = 'PY'
    group by isin, metric_id, dimension_key, value_fiscal_year_label
)

select
    originals.isin,
    originals.symbol,
    originals.metric_id,
    originals.dimension_key,
    originals.value_fiscal_year_label,
    originals.original_filing_id,
    comparatives.later_filing_id,
    originals.original_value,
    comparatives.restated_value,
    comparatives.restated_value / originals.original_value as ratio,
    originals.unit_resolution_method
from originals
inner join comparatives
    on
        originals.isin = comparatives.isin
        and originals.metric_id = comparatives.metric_id
        and originals.dimension_key = comparatives.dimension_key
        and originals.value_fiscal_year_label = comparatives.value_fiscal_year_label
where
    originals.original_value > 0
    and comparatives.restated_value > 0
    and {{ is_scale_error('comparatives.restated_value / originals.original_value') }}
