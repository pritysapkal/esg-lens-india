-- Semantic-layer view of fct_restatement: one row per compared pair, without the original and
-- restated values. The financial year of a pair is the year the value BELONGS to (year Y, not
-- the year of the report that restates it); the company-year key and the year-end date follow
-- that year, so restatement metrics line up with the other metrics of the same year.

select
    restatement.isin || '|' || restatement.value_fiscal_year_label as company_year_key,
    fiscal_year.end_date as fiscal_year_end,
    restatement.isin,
    restatement.value_fiscal_year_label as fiscal_year_label,
    restatement.restating_fiscal_year_label,
    restatement.metric_id,
    restatement.dimension_key,
    restatement.classification,
    restatement.is_compared,
    restatement.explained_by,
    restatement.flatters_trend,
    restatement.red_flag,
    restatement.is_metric_material
from {{ ref('fct_restatement') }} as restatement
inner join {{ ref('dim_fiscal_year') }} as fiscal_year
    on restatement.value_fiscal_year_label = fiscal_year.fiscal_year_label
