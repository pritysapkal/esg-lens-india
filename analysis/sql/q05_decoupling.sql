-- Q5. Decoupling: who grew while emitting less?
--
-- Business question  Between the first and the latest financial year, which companies grew
--                    their turnover AND cut their absolute Scope 1+2 emissions (absolute
--                    decoupling), and which only cut emissions per rupee (relative decoupling)?
-- Stakeholder        Climate-transition analyst: intensity can fall while the atmosphere sees
--                    more carbon; only absolute decoupling lowers emissions.
-- Method             Balanced panel: companies with emissions and turnover in every year and no
--                    comparability break after the first year. Compare first and latest year:
--                      absolute decoupling = turnover up, emissions down
--                      relative decoupling = turnover up, emissions up, intensity down
--                      no decoupling       = turnover up, intensity not down
--                      turnover fell       = shown apart, the question does not apply
-- SQL techniques     HAVING on per-company counts, conditional pivot of first and latest year
--                    (MAX CASE), CASE classification, share of group with SUM OVER an aggregate,
--                    total row by UNION ALL.
-- Caveats            Turnover is in current rupees: part of every company's "growth" is
--                    inflation, which makes decoupling look easier than it is. Two end points
--                    only, so one unusual year at either end decides the class. Scope 1+2 only.
--                    The company list holds changes of filed figures and stays local; counts and
--                    shares are published.

-- result: decoupling_by_company
with years as (
    select
        count(distinct fiscal_year_label) as n_years,
        min(fiscal_year_label) as first_year,
        max(fiscal_year_label) as latest_year
    from fct_company_year
),

balanced as (
    select
        company_year.isin,
        any_value(company_year.display_name) as display_name,
        any_value(company_year.sector_group) as sector_group,
        any_value(company_year.peer_group) as peer_group,
        max(
            case
                when company_year.fiscal_year_label = years.first_year
                    then company_year.turnover_cr
            end
        ) as turnover_first,
        max(
            case
                when company_year.fiscal_year_label = years.latest_year
                    then company_year.turnover_cr
            end
        ) as turnover_latest,
        max(
            case
                when company_year.fiscal_year_label = years.first_year
                    then company_year.ghg_s12_tco2e
            end
        ) as emissions_first,
        max(
            case
                when company_year.fiscal_year_label = years.latest_year
                    then company_year.ghg_s12_tco2e
            end
        ) as emissions_latest
    from fct_company_year as company_year
    cross join years
    group by company_year.isin, years.n_years, years.first_year
    having
        count(*) = years.n_years
        and count(company_year.ghg_intensity_tco2e_per_cr) = years.n_years
        and not bool_or(
            company_year.has_comparability_break
            and company_year.fiscal_year_label > years.first_year
        )
),

changes as (
    select
        display_name,
        sector_group,
        peer_group,
        100 * (turnover_latest / turnover_first - 1) as turnover_change_pct,
        100 * (emissions_latest / emissions_first - 1) as emissions_change_pct,
        100 * ((emissions_latest / turnover_latest) / (emissions_first / turnover_first) - 1)
            as intensity_change_pct
    from balanced
    where turnover_first > 0 and emissions_first > 0
)

select
    sector_group,
    peer_group,
    display_name,
    round(turnover_change_pct, 1) as turnover_change_pct,
    round(emissions_change_pct, 1) as emissions_change_pct,
    round(intensity_change_pct, 1) as intensity_change_pct,
    case
        when turnover_change_pct <= 0 then 'turnover fell'
        when emissions_change_pct < 0 then 'absolute decoupling'
        when intensity_change_pct < 0 then 'relative decoupling'
        else 'no decoupling'
    end as decoupling_class
from changes
order by decoupling_class, emissions_change_pct;

-- result: decoupling_by_sector_group
with years as (
    select
        count(distinct fiscal_year_label) as n_years,
        min(fiscal_year_label) as first_year,
        max(fiscal_year_label) as latest_year
    from fct_company_year
),

balanced as (
    select
        company_year.isin,
        any_value(company_year.sector_group) as sector_group,
        max(
            case
                when company_year.fiscal_year_label = years.first_year
                    then company_year.turnover_cr
            end
        ) as turnover_first,
        max(
            case
                when company_year.fiscal_year_label = years.latest_year
                    then company_year.turnover_cr
            end
        ) as turnover_latest,
        max(
            case
                when company_year.fiscal_year_label = years.first_year
                    then company_year.ghg_s12_tco2e
            end
        ) as emissions_first,
        max(
            case
                when company_year.fiscal_year_label = years.latest_year
                    then company_year.ghg_s12_tco2e
            end
        ) as emissions_latest
    from fct_company_year as company_year
    cross join years
    group by company_year.isin, years.n_years, years.first_year
    having
        count(*) = years.n_years
        and count(company_year.ghg_intensity_tco2e_per_cr) = years.n_years
        and not bool_or(
            company_year.has_comparability_break
            and company_year.fiscal_year_label > years.first_year
        )
),

classified as (
    select
        sector_group,
        case
            when turnover_latest <= turnover_first then 'turnover fell'
            when emissions_latest < emissions_first then 'absolute decoupling'
            when emissions_latest / turnover_latest < emissions_first / turnover_first
                then 'relative decoupling'
            else 'no decoupling'
        end as decoupling_class
    from balanced
    where turnover_first > 0 and emissions_first > 0
),

with_total as (
    select
        sector_group,
        decoupling_class
    from classified
    union all
    select
        'All sector groups' as sector_group,
        decoupling_class
    from classified
)

select
    sector_group,
    decoupling_class,
    count(*) as n_companies,
    sum(count(*)) over (partition by sector_group) as n_companies_in_panel,
    round(100.0 * count(*) / sum(count(*)) over (partition by sector_group), 1)
        as share_of_panel_pct
from with_total
group by sector_group, decoupling_class
order by sector_group, decoupling_class;
