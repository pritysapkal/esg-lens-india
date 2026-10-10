-- Validity ranges of one company never overlap, run in order, and have no end before their start.
with ordered as (
    select
        *,
        lead(valid_from_fy) over (partition by isin order by valid_from_fy) as next_valid_from_fy
    from {{ ref('dim_company_history') }}
)

select *  -- noqa: AM04
from ordered
where
    (valid_to_fy is not null and valid_to_fy < valid_from_fy)
    or (
        next_valid_from_fy is not null
        and (valid_to_fy is null or valid_to_fy >= next_valid_from_fy)
    )
