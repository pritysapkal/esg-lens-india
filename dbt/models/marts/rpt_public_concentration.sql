-- PUBLIC concentration of Scope 1+2 emissions, one row per company and financial year: the
-- company's rank by emissions, its share of the emissions of all companies covered that year,
-- the cumulative share from the largest emitter down, and top-5 / top-10 flags. The same
-- ranking as Week 10 Q2 (analysis/sql/q02_emission_concentration.sql).
-- Shares and ranks only: no tonnes and no total. A share cannot give back a filed value without
-- the total, which is published nowhere (docs/publication_policy.md). "Total" = the companies
-- in this project that year, not India. Numeric columns must be public_safe rows of the
-- kpi_catalogue seed for this model; assert_public_models_safe checks it on every build.
-- The 5-company rule of every public table: in a year with fewer than 5 companies the shares
-- are empty and suppressed_reason says so (ranks and flags stay). Never the case in the real
-- data (47 to 51 companies a year); it is in the synthetic CI data.

with ranked as (
    select
        isin,
        symbol,
        display_name,
        fiscal_year_label,
        sector_group,
        peer_group,
        ranking_group,
        ghg_s12_tco2e,
        row_number() over (
            partition by fiscal_year_label
            order by ghg_s12_tco2e desc, isin asc
        ) as emitter_rank,
        count(*) over (partition by fiscal_year_label) as n_companies_in_year,
        sum(ghg_s12_tco2e) over (partition by fiscal_year_label) as year_total
    from {{ ref('fct_company_year') }}
    where ghg_s12_tco2e is not null
)

select
    isin,
    symbol,
    display_name,
    fiscal_year_label,
    sector_group,
    peer_group,
    ranking_group,
    cast(emitter_rank as integer) as emitter_rank,
    cast(n_companies_in_year as integer) as n_companies_in_year,
    case
        when n_companies_in_year >= 5 then 100 * ghg_s12_tco2e / nullif(year_total, 0)
    end as share_of_total_pct,
    case
        when n_companies_in_year >= 5
            then
                100 * sum(ghg_s12_tco2e) over (
                    partition by fiscal_year_label
                    order by emitter_rank
                    rows between unbounded preceding and current row
                ) / nullif(year_total, 0)
    end as cumulative_share_pct,
    emitter_rank <= 5 as is_top_5,
    emitter_rank <= 10 as is_top_10,
    case when n_companies_in_year < 5 then 'fewer_than_5_companies' end as suppressed_reason
from ranked
