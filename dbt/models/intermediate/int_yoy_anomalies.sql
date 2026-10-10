-- Company-years where turnover or headcount moves by more than 40% against the company's
-- previous year in the data. Turnover is annualised (x annualisation_factor) so a 15-month year
-- is compared with 12-month years. explained_by says whether a corporate event or a change of
-- reporting boundary is flagged for that year; empty = unexplained, to be reviewed by a person.
-- Input for the Disclosure Quality Score (consistency checks); see docs/business_rules.md.

with years as (
    select
        isin,
        symbol,
        fiscal_year_label,
        has_event_break,
        boundary_changed_vs_prior,
        turnover_inr * annualisation_factor as turnover_annualised,
        total_headcount,
        lag(fiscal_year_label) over w as prior_fiscal_year_label,
        lag(turnover_inr * annualisation_factor) over w as prior_turnover_annualised,
        lag(total_headcount) over w as prior_total_headcount
    from {{ ref('dim_company_year') }}
    window w as (partition by isin order by fiscal_year_label)
),

measures as (
    select
        isin,
        symbol,
        fiscal_year_label,
        prior_fiscal_year_label,
        has_event_break,
        boundary_changed_vs_prior,
        'turnover_inr' as metric,
        prior_turnover_annualised as prior_value,
        turnover_annualised as current_value
    from years
    union all
    select
        isin,
        symbol,
        fiscal_year_label,
        prior_fiscal_year_label,
        has_event_break,
        boundary_changed_vs_prior,
        'total_headcount' as metric,
        prior_total_headcount as prior_value,
        total_headcount as current_value
    from years
)

select
    isin,
    symbol,
    fiscal_year_label,
    prior_fiscal_year_label,
    metric,
    prior_value as prior,  -- noqa: RF04
    current_value as current,  -- noqa: RF04
    current_value / prior_value - 1 as pct_change,
    case
        when has_event_break and boundary_changed_vs_prior then 'event + boundary change'
        when has_event_break then 'event'
        when boundary_changed_vs_prior then 'boundary change'
    end as explained_by
from measures
where prior_value > 0 and abs(current_value / prior_value - 1) > 0.4
