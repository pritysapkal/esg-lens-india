-- Semantic-layer view of fct_company_year: the same rows and columns, plus the two columns
-- MetricFlow needs - one key for the company-year and the financial year as a date (its END date,
-- 31 March). The peer group, sector group, ranking group, size band and ownership type of this
-- view are the shared dimensions of every metric. Local only: it holds raw filed values.
-- Metrics on it are generated from the kpi_catalogue seed (scripts/build_semantic_layer.py).

select
    company_year.isin || '|' || company_year.fiscal_year_label as company_year_key,
    fiscal_year.end_date as fiscal_year_end,
    -- every column, so a new catalogue metric needs no change here
    company_year.*  -- noqa: AM04
from {{ ref('fct_company_year') }} as company_year
inner join {{ ref('dim_fiscal_year') }} as fiscal_year
    on company_year.fiscal_year_label = fiscal_year.fiscal_year_label
