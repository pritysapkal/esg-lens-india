-- Real data: the peer_groups seed has exactly 51 symbols (NIFTY 50 + WIPRO), each one is the
-- current symbol of a company in dim_company, and no company is left without a peer group.
{{ config(tags=['realdata']) }}

select 'seed does not have 51 symbols' as problem
where (select count(*) from {{ ref('peer_groups') }}) != 51

union all

select 'seed symbol without company: ' || peer_groups.symbol as problem
from {{ ref('peer_groups') }} as peer_groups
left join {{ ref('dim_company') }} as dim_company on peer_groups.symbol = dim_company.current_symbol
where dim_company.isin is null

union all

select 'company without peer group: ' || current_symbol as problem
from {{ ref('dim_company') }}
where peer_group is null
