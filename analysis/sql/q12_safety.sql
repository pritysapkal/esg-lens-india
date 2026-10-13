-- Q12. Safety: where do people die at work, and at which companies more than once?
--
-- Business question  How many work-related deaths are there per 10,000 people in the workforce,
--                    by sector group and year, and which companies report a fatality in two or
--                    more of the years covered?
-- Stakeholder        Board safety committee, lender or insurer; anyone who treats a repeated
--                    fatality as a governance signal.
-- Method             Group rate = sum of fatalities / sum of workforce x 10,000 over the
--                    companies that report both (ratio of sums: a large employer weighs more,
--                    as it should for "risk per person"). Shown only for 5 companies or more.
--                    Repeat = the yes / no flag "any fatality" is true in at least two years.
-- SQL techniques     Ratio of sums with a pre-filtered CTE, CASE for the group-size rule,
--                    UNION ALL total row, HAVING on a conditional count, STRING_AGG of the years.
-- Caveats            Fatalities cover employees and workers as filed; contract workers are
--                    included only as far as the company counts them, and practice differs. A
--                    zero can mean a safe year or weak recording. Workforce is a year-end
--                    headcount, not hours worked. One accident can decide a group's rate for a
--                    year. The second result shows the flag only; the number of deaths per
--                    company is a raw filed count and stays local.

-- result: fatality_rate_by_sector_group
with reported as (
    -- only company-years with both figures, so that sums and counts cover the same companies
    select
        isin,
        sector_group,
        fiscal_year_label,
        fatalities_total,
        headcount_total,
        any_fatality
    from fct_company_year
    where fatalities_total is not null and headcount_total > 0
),

with_total as (
    select
        sector_group,
        fiscal_year_label,
        isin,
        fatalities_total,
        headcount_total,
        any_fatality
    from reported
    union all
    select
        'All companies' as sector_group,
        fiscal_year_label,
        isin,
        fatalities_total,
        headcount_total,
        any_fatality
    from reported
),

by_group as (
    select
        sector_group,
        fiscal_year_label,
        count(distinct isin) as n_companies,
        10000 * sum(fatalities_total) / sum(headcount_total) as fatalities_per_10k_agg,
        count(*) filter (where any_fatality) as n_companies_with_fatality
    from with_total
    group by sector_group, fiscal_year_label
)

select
    sector_group,
    fiscal_year_label,
    n_companies,
    case when n_companies >= 5 then round(fatalities_per_10k_agg, 2) end
        as fatalities_per_10k_workforce_agg,
    n_companies_with_fatality,
    case when n_companies >= 5 then round(100.0 * n_companies_with_fatality / n_companies, 1) end
        as share_of_companies_with_fatality_pct
from by_group
order by sector_group, fiscal_year_label;

-- result: companies_with_repeated_fatalities
select
    sector_group,
    peer_group,
    display_name,
    count(*) as n_years_reported,
    count(*) filter (where any_fatality) as n_years_with_fatality,
    string_agg(fiscal_year_label, ', ' order by fiscal_year_label) filter (where any_fatality)
        as years_with_fatality
from fct_company_year
group by sector_group, peer_group, display_name
having count(*) filter (where any_fatality) >= 2
order by n_years_with_fatality desc, sector_group asc, display_name asc;
