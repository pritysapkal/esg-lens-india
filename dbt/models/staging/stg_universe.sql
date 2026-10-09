-- Official NIFTY 50 constituents (niftyindices.com), trimmed and snake_cased.

with universe as (
    select * from {{ source('intake', 'universe') }}
)

select
    trim(symbol) as symbol,
    trim(company_name) as company_name,
    trim(industry) as industry,
    trim(series) as series,
    trim(isin_code) as isin
from universe
