-- One row per company, keyed by ISIN: current identity, filing coverage, NIFTY 50 membership,
-- NSE industry, peer group and NIC sector (from the latest filing with a usable NIC code).
-- Primary NIC = the code with the highest turnover share (ties -> lowest code). Conglomerate =
-- top NIC division below 60% of turnover, or three or more divisions with at least 15% each.

with names as (
    select
        *,
        row_number() over (partition by isin order by fiscal_year_label desc) as recency
    from {{ ref('int_company_names') }}
),

current_identity as (
    select
        isin,
        company_name_clean as current_name,
        symbol as current_symbol
    from names
    where recency = 1
),

latest_cin as (
    select
        isin,
        arg_max(cin, fiscal_year_label) filter (where cin is not null) as cin
    from names
    group by isin
),

coverage as (
    select
        isin,
        min(fiscal_year_label) as first_fy,
        max(fiscal_year_label) as last_fy,
        count(*) as n_filings,
        string_agg(distinct symbol, ', ') as all_symbols
    from {{ ref('stg_filings') }}
    group by isin
),

nic_rows as (
    select * from {{ ref('int_company_nic') }}
    where nic_code is not null
),

nic_latest_fy as (
    select
        isin,
        max(fiscal_year_label) as nic_fiscal_year_label
    from nic_rows
    group by isin
),

nic_latest as (
    select nic_rows.*
    from nic_rows
    inner join nic_latest_fy
        on
            nic_rows.isin = nic_latest_fy.isin
            and nic_rows.fiscal_year_label = nic_latest_fy.nic_fiscal_year_label
),

nic_codes as (
    select distinct
        isin,
        nic_code,
        nic_code_share,
        is_primary_in_filing
    from nic_latest
),

nic_divisions as (
    select distinct
        isin,
        nic_division_2d,
        nic_division_share
    from nic_latest
),

division_summary as (
    select
        isin,
        max(nic_division_share) as top_division_share,
        count(*) filter (where round(nic_division_share, 4) >= 0.15) as n_divisions_ge_15pct
    from nic_divisions
    group by isin
),

ranked_codes as (
    select
        *,
        row_number() over (partition by isin order by nic_code_share desc, nic_code asc) as rn
    from nic_codes
),

top_codes as (
    select
        isin,
        string_agg(
            nic_code || ' (' || cast(round(nic_code_share * 100, 1) as varchar) || '%)',
            '; ' order by nic_code_share desc, nic_code asc
        ) as top_3_nic_codes
    from ranked_codes
    where rn <= 3
    group by isin
),

primary_nic as (
    select
        isin,
        min(nic_code) as nic_primary_code
    from nic_codes
    where is_primary_in_filing
    group by isin
),

universe as (
    select
        isin,
        industry
    from {{ ref('stg_universe') }}
)

select
    current_identity.isin,
    current_identity.current_name,
    current_identity.current_symbol,
    latest_cin.cin,
    coverage.all_symbols,
    coverage.first_fy,
    coverage.last_fy,
    coverage.n_filings,
    universe.isin is not null as in_universe,
    universe.industry as nse_industry,
    peer_groups.peer_group,
    primary_nic.nic_primary_code,
    left(primary_nic.nic_primary_code, 2) as nic_division_2d,
    nic_sector_map.nic_division_name,
    nic_latest_fy.nic_fiscal_year_label,
    division_summary.top_division_share as nic_top_division_share,
    division_summary.n_divisions_ge_15pct as nic_n_divisions_ge_15pct,
    top_codes.top_3_nic_codes,
    case
        when division_summary.isin is null then null
        else
            division_summary.top_division_share < 0.6
            or division_summary.n_divisions_ge_15pct >= 3
    end as is_conglomerate
from current_identity
left join latest_cin on current_identity.isin = latest_cin.isin
left join coverage on current_identity.isin = coverage.isin
left join universe on current_identity.isin = universe.isin
left join {{ ref('peer_groups') }} as peer_groups
    on current_identity.current_symbol = peer_groups.symbol
left join primary_nic on current_identity.isin = primary_nic.isin
left join nic_latest_fy on current_identity.isin = nic_latest_fy.isin
left join division_summary on current_identity.isin = division_summary.isin
left join top_codes on current_identity.isin = top_codes.isin
left join {{ ref('nic_sector_map') }} as nic_sector_map
    on left(primary_nic.nic_primary_code, 2) = nic_sector_map.nic_division_2d
