-- Real data (checked by hand against the filings):
--  * HDFCBANK: peer group Financials, primary NIC division 64.
--  * TMPV (Tata Motors Passenger Vehicles) has ISIN INE155A01022.
--  * ETERNAL: the filings only contain the name Eternal (FY2024-25 onwards); if an older name
--    ever appears it must be Zomato, and exactly one row is current.
{{ config(tags=['realdata']) }}

select 'HDFCBANK is not Financials / division 64' as problem
where
    (
        select count(*) from {{ ref('dim_company') }}
        where current_symbol = 'HDFCBANK' and peer_group = 'Financials' and nic_division_2d = '64'
    ) != 1

union all

select 'TMPV ISIN is not INE155A01022' as problem
where
    (
        select count(*) from {{ ref('dim_company') }}
        where current_symbol = 'TMPV' and isin = 'INE155A01022'
    ) != 1

union all

select 'ETERNAL history has a name other than Eternal / Zomato: ' || company_name as problem
from {{ ref('dim_company_history') }}
where
    isin = 'INE758T01015'
    and company_name not like 'Eternal%'
    and company_name not like 'Zomato%'

union all

select 'ETERNAL does not have exactly one current Eternal row' as problem
where
    (
        select count(*) from {{ ref('dim_company_history') }}
        where isin = 'INE758T01015' and is_current and company_name like 'Eternal%'
    ) != 1
