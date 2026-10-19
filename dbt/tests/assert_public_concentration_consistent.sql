-- rpt_public_concentration must be a proper Pareto table. Rows returned are violations: per
-- financial year the shares add up to 100, the cumulative share of the last emitter is 100,
-- ranks run 1..n without gaps, and exactly min(5, n) and min(10, n) companies carry the top-5
-- and top-10 flags. A year with fewer than 5 companies has no shares (5-company rule): its
-- shares must all be empty instead.

with by_year as (
    select
        fiscal_year_label,
        count(*) as n_rows,
        max(n_companies_in_year) as n_companies,
        sum(share_of_total_pct) as share_sum,
        max(cumulative_share_pct) filter (where emitter_rank = n_companies_in_year)
            as last_cumulative,
        count(distinct emitter_rank) as n_ranks,
        max(emitter_rank) as max_rank,
        count(*) filter (where is_top_5) as n_top_5,
        count(*) filter (where is_top_10) as n_top_10
    from {{ ref('rpt_public_concentration') }}
    group by fiscal_year_label
)

select
    fiscal_year_label,
    n_rows,
    share_sum,
    last_cumulative,
    n_top_5,
    n_top_10
from by_year
where
    (n_companies >= 5 and (abs(share_sum - 100) > 1e-6 or abs(last_cumulative - 100) > 1e-6))
    or (n_companies < 5 and (share_sum is not null or last_cumulative is not null))
    or n_ranks != n_rows
    or max_rank != n_rows
    or n_companies != n_rows
    or n_top_5 != least(5, n_rows)
    or n_top_10 != least(10, n_rows)
