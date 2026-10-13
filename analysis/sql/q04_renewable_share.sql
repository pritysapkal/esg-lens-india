-- Q4. Renewable energy: which peer groups are switching, and who crossed 50%?
--
-- Business question  How did the renewable share of energy move in each peer group, and which
--                    companies went from below half to at least half renewable, in which year?
-- Stakeholder        Sustainability lead benchmarking the company's energy transition.
-- Method             Peer-group share = sum of renewable energy / sum of total energy over the
--                    companies that report both (ratio of sums, never an average of shares).
--                    Shown only for 5 companies or more. A crossing = below 50% in one year and
--                    at 50% or more in the next year the company reports.
-- SQL techniques     Ratio of sums, CASE for the group-size rule, LAG over a named WINDOW,
--                    QUALIFY with MIN OVER to keep the first crossing only.
-- Caveats            A high share at an office-only company means much less energy than the same
--                    share at a factory; the peer-group figure is weighted by energy, so big
--                    users dominate. Four peer groups have fewer than 5 companies and show no
--                    figure. Seven energy totals were suspected scale errors and use the value
--                    of the later report.

-- result: renewable_share_by_peer_group
with reported as (
    -- only company-years with both figures, so that sums and counts cover the same companies
    select
        isin,
        peer_group,
        fiscal_year_label,
        energy_renewable_gj,
        energy_total_gj
    from fct_company_year
    where renewable_share_pct is not null
),

by_group as (
    select
        peer_group,
        fiscal_year_label,
        count(distinct isin) as n_companies,
        100 * sum(energy_renewable_gj) / sum(energy_total_gj) as renewable_share_agg
    from reported
    group by peer_group, fiscal_year_label
)

select
    peer_group,
    fiscal_year_label,
    n_companies,
    case when n_companies >= 5 then round(renewable_share_agg, 1) end as renewable_share_agg_pct,
    case
        when n_companies >= 5
            then
                round(
                    renewable_share_agg
                    - lag(renewable_share_agg) over (
                        partition by peer_group
                        order by fiscal_year_label
                    ),
                    1
                )
    end as change_vs_previous_year_pp,
    case when n_companies < 5 then 'fewer_than_5_companies' end as suppressed_reason
from by_group
order by peer_group, fiscal_year_label;

-- result: companies_crossing_50_pct
with shares as (
    select
        display_name,
        peer_group,
        fiscal_year_label,
        renewable_share_pct,
        lag(renewable_share_pct) over company_years as previous_share_pct,
        lag(fiscal_year_label) over company_years as previous_fiscal_year_label
    from fct_company_year
    where renewable_share_pct is not null
    window company_years as (partition by isin order by fiscal_year_label)
)

select
    display_name,
    peer_group,
    fiscal_year_label as crossed_in_year,
    previous_fiscal_year_label as previous_year,
    round(previous_share_pct, 1) as share_before_pct,
    round(renewable_share_pct, 1) as share_after_pct
from shares
where previous_share_pct < 50 and renewable_share_pct >= 50
-- the first crossing of each company only
qualify fiscal_year_label = min(fiscal_year_label) over (partition by display_name)
order by crossed_in_year, display_name;
