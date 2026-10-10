-- Real data: every ranking group has at least 5 companies, and a company is only ranked at
-- peer-group level when its peer group has 5 or more companies and is not "Industrials & others".
{{ config(tags=['realdata']) }}

select
    ranking_group,
    count(*) as n_companies
from {{ ref('dim_company') }}
group by ranking_group
having count(*) < 5

union all

select
    current_symbol as ranking_group,
    peer_group_n as n_companies
from {{ ref('dim_company') }}
where
    ranking_basis = 'peer_group'
    and (peer_group_n < 5 or peer_group = 'Industrials & others')
