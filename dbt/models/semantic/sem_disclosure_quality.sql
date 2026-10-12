-- Semantic-layer view of fct_disclosure_quality: the same rows and columns, plus the company-year
-- key and the financial year as a date (its END date, 31 March). Group dimensions (peer group,
-- sector group, ...) are joined from sem_company_year by MetricFlow, so they are defined once.

select
    disclosure_quality.isin || '|' || disclosure_quality.fiscal_year_label as company_year_key,
    fiscal_year.end_date as fiscal_year_end,
    -- every column, as in sem_company_year
    disclosure_quality.*  -- noqa: AM04
from {{ ref('fct_disclosure_quality') }} as disclosure_quality
inner join {{ ref('dim_fiscal_year') }} as fiscal_year
    on disclosure_quality.fiscal_year_label = fiscal_year.fiscal_year_label
