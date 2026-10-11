-- Disclosure rate of every Leadership (voluntary) indicator: the share of company-years, among
-- those whose taxonomy has the indicator, that filed a substantive value for it.
--   carries_information = false when every company-year or no company-year discloses it: such an
--   indicator cannot tell two companies apart (it still counts in voluntary depth).
-- An indicator renamed between taxonomy versions appears once per name.
-- Run:  dbt show --select dqs_leadership_disclosure_rates --limit 100 --profiles-dir .
-- Results are written up in docs/disclosure_quality_score.md.

select
    principle,
    indicator,
    min(fiscal_year_label) as first_fiscal_year,
    max(fiscal_year_label) as last_fiscal_year,
    count(*) as n_company_years,
    count(*) filter (where is_disclosed) as n_disclosed,
    round(100.0 * count(*) filter (where is_disclosed) / count(*), 1) as disclosure_rate_pct,
    count(*) filter (where is_disclosed) not in (0, count(*)) as carries_information
from {{ ref('int_dqs_leadership_disclosure') }}
group by principle, indicator
order by disclosure_rate_pct desc, principle asc, indicator asc
