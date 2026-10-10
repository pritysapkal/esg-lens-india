-- Slowly changing dimension (type 2) of company name and symbol, derived from the filing history.
-- One row per run of consecutive financial years in which the company filed under the same
-- name and symbol. valid_to_fy is the last year seen with that name; it is empty for the current
-- row. Derived, not a dbt snapshot: see docs/adr/0003-company-history-scd2.md.

with names as (
    select
        isin,
        fiscal_year_label,
        company_name_clean as company_name,
        symbol,
        lag(company_name_clean) over (partition by isin order by fiscal_year_label) as prev_name,
        lag(symbol) over (partition by isin order by fiscal_year_label) as prev_symbol
    from {{ ref('int_company_names') }}
),

runs as (
    select
        *,
        sum(
            case
                when prev_name is null or prev_name != company_name or prev_symbol != symbol
                    then 1
                else 0
            end
        ) over (partition by isin order by fiscal_year_label) as run_id
    from names
),

grouped as (
    select
        isin,
        run_id,
        company_name,
        symbol,
        min(fiscal_year_label) as valid_from_fy,
        max(fiscal_year_label) as last_seen_fy,
        count(*) as n_years
    from runs
    group by isin, run_id, company_name, symbol
)

select
    isin,
    company_name,
    symbol,
    valid_from_fy,
    case
        when run_id = max(run_id) over (partition by isin) then null
        else last_seen_fy
    end as valid_to_fy,
    run_id = max(run_id) over (partition by isin) as is_current,
    n_years,
    run_id as version_number
from grouped
