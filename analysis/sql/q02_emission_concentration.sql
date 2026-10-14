-- Q2. Concentration: how few companies carry most of the emissions?
--
-- Business question  What share of the total Scope 1+2 emissions of the companies covered is
--                    held by the 5 and by the 10 largest emitters, each year?
-- Stakeholder        Climate-risk analyst: where does engagement move the total most?
-- Method             Rank companies by Scope 1+2 emissions within each year, divide each by the
--                    year's total and add the shares up from the top (a Pareto table).
-- SQL techniques     Window functions: ROW_NUMBER, SUM OVER (share of total), running total
--                    with an explicit frame; QUALIFY; conditional aggregation.
-- Caveats            "Total" means the companies in this project (NIFTY 50 plus one), not India.
--                    Scope 1+2 only: the Scope 3 of a refiner or a bank is not in here. The
--                    company shares are published as shares only, in the public model
--                    rpt_public_concentration (same ranking); tonnes and totals stay local.

-- result: pareto_top10_by_year
with ranked as (
    select
        fiscal_year_label,
        display_name,
        sector_group,
        peer_group,
        ghg_s12_tco2e,
        row_number() over (
            partition by fiscal_year_label
            order by ghg_s12_tco2e desc
        ) as emitter_rank,
        sum(ghg_s12_tco2e) over (partition by fiscal_year_label) as total_tco2e
    from fct_company_year
    where ghg_s12_tco2e is not null
)

select
    fiscal_year_label,
    emitter_rank,
    display_name,
    sector_group,
    peer_group,
    round(100 * ghg_s12_tco2e / total_tco2e, 1) as share_of_total_pct,
    round(
        100 * sum(ghg_s12_tco2e) over (
            partition by fiscal_year_label
            order by emitter_rank
            rows between unbounded preceding and current row
        ) / total_tco2e,
        1
    ) as cumulative_share_pct
from ranked
qualify emitter_rank <= 10
order by fiscal_year_label, emitter_rank;

-- result: concentration_by_year
with ranked as (
    select
        fiscal_year_label,
        ghg_s12_tco2e,
        row_number() over (
            partition by fiscal_year_label
            order by ghg_s12_tco2e desc
        ) as emitter_rank
    from fct_company_year
    where ghg_s12_tco2e is not null
),

running as (
    select
        fiscal_year_label,
        emitter_rank,
        sum(ghg_s12_tco2e) over (
            partition by fiscal_year_label
            order by emitter_rank
            rows between unbounded preceding and current row
        ) / sum(ghg_s12_tco2e) over (partition by fiscal_year_label) as cumulative_share
    from ranked
)

select
    fiscal_year_label,
    count(*) as n_companies,
    round(100 * max(case when emitter_rank = 1 then cumulative_share end), 1) as top_1_share_pct,
    round(100 * max(case when emitter_rank = 5 then cumulative_share end), 1) as top_5_share_pct,
    round(100 * max(case when emitter_rank = 10 then cumulative_share end), 1)
        as top_10_share_pct,
    -- how many companies it takes to reach 80% and 90% of the total
    min(case when cumulative_share >= 0.8 then emitter_rank end) as companies_for_80_pct,
    min(case when cumulative_share >= 0.9 then emitter_rank end) as companies_for_90_pct
from running
group by fiscal_year_label
order by fiscal_year_label;
