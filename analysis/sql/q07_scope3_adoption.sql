-- Q7. Scope 3: how many companies disclose value-chain emissions?
--
-- Business question  What share of companies gives a Scope 3 emissions figure, by sector group
--                    and year - and is the voluntary disclosure spreading?
-- Stakeholder        Regulator or standard-setter judging whether a voluntary (Leadership)
--                    indicator is becoming normal practice.
-- Method             Share = company reports with a Scope 3 value / company reports, per sector
--                    group and year, plus a row for all companies. Years are turned into
--                    columns so that the trend reads left to right.
-- SQL techniques     UNION ALL for the total row, conditional aggregation, PIVOT (DuckDB) with
--                    two aggregates per year, CTE feeding a PIVOT statement.
-- Caveats            "Disclosed" means a number is in the filing: it says nothing about how many
--                    of the 15 Scope 3 categories are covered, so shares are not comparable in
--                    depth. A filed zero counts as disclosed. Sector groups all have 5 or more
--                    companies in every year, so nothing is withheld.

-- result: scope3_adoption_by_sector_group
with reports as (
    select
        sector_group,
        fiscal_year_label,
        scope3_disclosed
    from fct_company_year
    union all
    select
        'All companies' as sector_group,
        fiscal_year_label,
        scope3_disclosed
    from fct_company_year
),

adoption as (
    select
        sector_group,
        fiscal_year_label,
        count(*) as n_companies,
        case
            when count(*) >= 5
                then round(100.0 * count(*) filter (where scope3_disclosed) / count(*), 1)
        end as scope3_share_pct
    from reports
    group by sector_group, fiscal_year_label
)

pivot adoption
on fiscal_year_label
using max(scope3_share_pct) as scope3_share_pct, max(n_companies) as n_companies
group by sector_group
order by sector_group;
