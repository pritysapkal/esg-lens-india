-- Real data: has_comparability_break is true for the five verified event breaks and for every
-- reporting-boundary switch (standalone <-> consolidated) seen in the filings, and boundary
-- switches carry the reason "boundary change". Rows returned are missing flags.
{{ config(tags=['realdata']) }}

with expected (symbol, fiscal_year_label, reason_contains) as (
    values
    ('HDFCBANK', 'FY2023-24', 'merger'),
    ('RELIANCE', 'FY2023-24', 'demerger'),
    ('ITC', 'FY2024-25', 'demerger'),
    ('TMPV', 'FY2025-26', 'demerger'),
    ('SHRIRAMFIN', 'FY2022-23', 'merger'),
    ('NTPC', 'FY2024-25', 'boundary change'),
    ('POWERGRID', 'FY2023-24', 'boundary change'),
    ('POWERGRID', 'FY2024-25', 'boundary change'),
    ('POWERGRID', 'FY2025-26', 'boundary change'),
    ('TATACONSUM', 'FY2024-25', 'boundary change'),
    ('TATASTEEL', 'FY2023-24', 'boundary change'),
    ('WIPRO', 'FY2023-24', 'boundary change'),
    ('WIPRO', 'FY2024-25', 'boundary change')
)

select
    expected.symbol,
    expected.fiscal_year_label,
    expected.reason_contains,
    company_year.has_comparability_break,
    company_year.comparability_break_reason
from expected
left join {{ ref('dim_company_year') }} as company_year
    on
        expected.symbol = company_year.symbol
        and expected.fiscal_year_label = company_year.fiscal_year_label
where
    company_year.isin is null
    or not company_year.has_comparability_break
    or company_year.comparability_break_reason not like '%' || expected.reason_contains || '%'

union all

-- the flag must also match the boundary switches in the data itself, row by row
select
    current_year.symbol,
    current_year.fiscal_year_label,
    'boundary switch not flagged' as reason_contains,
    current_year.has_comparability_break,
    current_year.comparability_break_reason
from {{ ref('dim_company_year') }} as current_year
inner join {{ ref('dim_company_year') }} as prior_year
    on
        current_year.isin = prior_year.isin
        and prior_year.fiscal_year_label = (
            select max(earlier.fiscal_year_label)
            from {{ ref('dim_company_year') }} as earlier
            where
                earlier.isin = current_year.isin
                and earlier.fiscal_year_label < current_year.fiscal_year_label
        )
where
    current_year.reporting_boundary != prior_year.reporting_boundary
    and not current_year.has_comparability_break
