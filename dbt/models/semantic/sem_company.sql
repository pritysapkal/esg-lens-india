-- Semantic-layer view of dim_company: the company names, so that any metric can be shown per
-- company (for example a company's Disclosure Quality Score by year in the report card).

select
    isin,
    display_name,
    current_symbol as symbol
from {{ ref('dim_company') }}
