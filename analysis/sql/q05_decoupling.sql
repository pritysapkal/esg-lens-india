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
--                    PLAUSIBILITY SCREEN, applied first. A company is "needs_review", and gets
--                    none of the classes above, when
--                      * its turnover or its emissions changed by more than -50% or +100%
--                        between the two end points. The panel holds no company with a merger,
--                        demerger or boundary change in between, so no recorded corporate
--                        event explains a change of that size; or
--                      * its turnover or its emissions have a one-year reversal in between: a
--                        year more than twice, or less than half of, both its neighbours (the
--                        screen of Q3).
--                    review_reason says which. A flagged company may be perfectly real (a fast
--                    grower); it is set aside until someone has read the report.
-- SQL techniques     HAVING on per-company counts, semi join, LAG and LEAD over a named WINDOW,
--                    BOOL_OR, conditional pivot of first and latest year (MAX CASE), CONCAT_WS
--                    for the reasons, CASE classification, share of group with SUM OVER an
--                    aggregate, total row by UNION ALL.
-- Caveats            Turnover is in current rupees: part of every company's "growth" is
--                    inflation, which makes decoupling look easier than it is. Two end points
--                    only, so one unusual year at either end decides the class. Scope 1+2 only.
--                    The thresholds of the screen are a rule of this analysis. The company list
--                    holds changes of filed figures and stays local; counts and shares are
--                    published.

-- result: decoupling_by_company
with years as (
    select
        count(distinct fiscal_year_label) as n_years,
        min(fiscal_year_label) as first_year,
        max(fiscal_year_label) as latest_year
    from fct_company_year
),

balanced_companies as (
    select company_year.isin
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

series as (
    select
        company_year.isin,
        company_year.display_name,
        company_year.sector_group,
        company_year.peer_group,
        company_year.fiscal_year_label,
        company_year.turnover_cr,
        company_year.ghg_s12_tco2e,
        lag(company_year.turnover_cr) over company_years as turnover_before,
        lead(company_year.turnover_cr) over company_years as turnover_after,
        lag(company_year.ghg_s12_tco2e) over company_years as emissions_before,
        lead(company_year.ghg_s12_tco2e) over company_years as emissions_after
    from fct_company_year as company_year
    semi join balanced_companies on company_year.isin = balanced_companies.isin
    window company_years as (
        partition by company_year.isin
        order by company_year.fiscal_year_label
    )
),

per_company as (
    select
        series.isin,
        any_value(series.display_name) as display_name,
        any_value(series.sector_group) as sector_group,
        any_value(series.peer_group) as peer_group,
        max(case when series.fiscal_year_label = years.first_year then series.turnover_cr end)
            as turnover_first,
        max(case when series.fiscal_year_label = years.latest_year then series.turnover_cr end)
            as turnover_latest,
        max(case when series.fiscal_year_label = years.first_year then series.ghg_s12_tco2e end)
            as emissions_first,
        max(case when series.fiscal_year_label = years.latest_year then series.ghg_s12_tco2e end)
            as emissions_latest,
        -- a middle year more than twice, or less than half of, both its neighbours
        coalesce(
            bool_or(
                series.turnover_cr > 2 * greatest(series.turnover_before, series.turnover_after)
                or series.turnover_cr < least(series.turnover_before, series.turnover_after) / 2
            ) filter (
                where series.turnover_before is not null and series.turnover_after is not null
            ),
            false
        ) as turnover_reverses,
        coalesce(
            bool_or(
                series.ghg_s12_tco2e
                > 2 * greatest(series.emissions_before, series.emissions_after)
                or series.ghg_s12_tco2e
                < least(series.emissions_before, series.emissions_after) / 2
            ) filter (
                where series.emissions_before is not null and series.emissions_after is not null
            ),
            false
        ) as emissions_reverse
    from series
    cross join years
    group by series.isin
),

changes as (
    select
        *,
        100 * (turnover_latest / turnover_first - 1) as turnover_change_pct,
        100 * (emissions_latest / emissions_first - 1) as emissions_change_pct,
        100 * ((emissions_latest / turnover_latest) / (emissions_first / turnover_first) - 1)
            as intensity_change_pct
    from per_company
    where turnover_first > 0 and emissions_first > 0
),

screened as (
    select
        *,
        nullif(
            concat_ws(
                ' + ',
                case
                    when turnover_change_pct < -50 or turnover_change_pct > 100
                        then 'turnover change beyond -50% / +100%'
                end,
                case
                    when emissions_change_pct < -50 or emissions_change_pct > 100
                        then 'emissions change beyond -50% / +100%'
                end,
                case when turnover_reverses then 'turnover: one-year reversal' end,
                case when emissions_reverse then 'emissions: one-year reversal' end
            ),
            ''
        ) as review_reason
    from changes
)

select
    sector_group,
    peer_group,
    display_name,
    round(turnover_change_pct, 1) as turnover_change_pct,
    round(emissions_change_pct, 1) as emissions_change_pct,
    round(intensity_change_pct, 1) as intensity_change_pct,
    case
        when review_reason is not null then 'needs_review'
        when turnover_change_pct <= 0 then 'turnover fell'
        when emissions_change_pct < 0 then 'absolute decoupling'
        when intensity_change_pct < 0 then 'relative decoupling'
        else 'no decoupling'
    end as decoupling_class,
    -- the class the company would have had without the plausibility screen
    case
        when turnover_change_pct <= 0 then 'turnover fell'
        when emissions_change_pct < 0 then 'absolute decoupling'
        when intensity_change_pct < 0 then 'relative decoupling'
        else 'no decoupling'
    end as class_before_screen,
    review_reason
from screened
order by decoupling_class, emissions_change_pct;

-- result: decoupling_by_sector_group
-- Counts per class, after the plausibility screen and (for comparison) before it.
with years as (
    select
        count(distinct fiscal_year_label) as n_years,
        min(fiscal_year_label) as first_year,
        max(fiscal_year_label) as latest_year
    from fct_company_year
),

balanced_companies as (
    select company_year.isin
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

series as (
    select
        company_year.isin,
        company_year.sector_group,
        company_year.fiscal_year_label,
        company_year.turnover_cr,
        company_year.ghg_s12_tco2e,
        lag(company_year.turnover_cr) over company_years as turnover_before,
        lead(company_year.turnover_cr) over company_years as turnover_after,
        lag(company_year.ghg_s12_tco2e) over company_years as emissions_before,
        lead(company_year.ghg_s12_tco2e) over company_years as emissions_after
    from fct_company_year as company_year
    semi join balanced_companies on company_year.isin = balanced_companies.isin
    window company_years as (
        partition by company_year.isin
        order by company_year.fiscal_year_label
    )
),

per_company as (
    select
        series.isin,
        any_value(series.sector_group) as sector_group,
        max(case when series.fiscal_year_label = years.first_year then series.turnover_cr end)
            as turnover_first,
        max(case when series.fiscal_year_label = years.latest_year then series.turnover_cr end)
            as turnover_latest,
        max(case when series.fiscal_year_label = years.first_year then series.ghg_s12_tco2e end)
            as emissions_first,
        max(case when series.fiscal_year_label = years.latest_year then series.ghg_s12_tco2e end)
            as emissions_latest,
        coalesce(
            bool_or(
                series.turnover_cr > 2 * greatest(series.turnover_before, series.turnover_after)
                or series.turnover_cr < least(series.turnover_before, series.turnover_after) / 2
                or series.ghg_s12_tco2e
                > 2 * greatest(series.emissions_before, series.emissions_after)
                or series.ghg_s12_tco2e
                < least(series.emissions_before, series.emissions_after) / 2
            ) filter (
                where series.turnover_before is not null and series.turnover_after is not null
            ),
            false
        ) as has_one_year_reversal
    from series
    cross join years
    group by series.isin
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
        end as class_before_screen,
        has_one_year_reversal
        or turnover_latest / turnover_first not between 0.5 and 2
        or emissions_latest / emissions_first not between 0.5 and 2 as needs_review
    from per_company
    where turnover_first > 0 and emissions_first > 0
),

with_total as (
    select
        sector_group,
        class_before_screen,
        needs_review
    from classified
    union all
    select
        'All sector groups' as sector_group,
        class_before_screen,
        needs_review
    from classified
),

-- every company once under its class after the screen and once under its class before it
both_views as (
    select
        sector_group,
        case when needs_review then 'needs_review' else class_before_screen end
            as decoupling_class,
        1 as n_after_screen,
        0 as n_before_screen
    from with_total
    union all
    select
        sector_group,
        class_before_screen as decoupling_class,
        0 as n_after_screen,
        1 as n_before_screen
    from with_total
)

select
    sector_group,
    decoupling_class,
    cast(sum(n_after_screen) as integer) as n_companies,
    cast(sum(sum(n_after_screen)) over (partition by sector_group) as integer)
        as n_companies_in_panel,
    round(
        100.0 * sum(n_after_screen) / sum(sum(n_after_screen)) over (partition by sector_group),
        1
    ) as share_of_panel_pct,
    cast(sum(n_before_screen) as integer) as n_companies_before_screen
from both_views
group by sector_group, decoupling_class
order by sector_group, decoupling_class;
