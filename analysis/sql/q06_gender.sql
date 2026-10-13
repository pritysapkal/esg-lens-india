-- Q6. Gender: are women a growing part of the workforce, and is the pay gap closing?
--
-- Business question  How did the share of women in the workforce and the pay-equity gap move in
--                    each sector group, and is the gap narrowing?
-- Stakeholder        Head of HR or a diversity-focused investor.
-- Method             Women in workforce = sum of women / sum of workforce over the companies of
--                    the group (ratio of sums). Pay-equity gap = women's share of wages minus
--                    women's share of headcount, in percentage points (negative = women get a
--                    smaller slice of pay than of jobs); the group figure is the MEDIAN company
--                    gap, because wages in rupees are not filed and a ratio of sums is not
--                    possible. Trend on a balanced panel: companies with the figure in every
--                    year it exists and no comparability break. The wage share is filed from
--                    FY2023-24, so the gap has one year less than the workforce share. Each
--                    company's gap is then sorted into moved closer to zero, moved away from
--                    zero, or unchanged (a move of 0.5 percentage points or less).
-- SQL techniques     Two balanced panels built with HAVING, UNION ALL of panels, ratio of sums,
--                    MEDIAN, FULL OUTER JOIN of two measures with different coverage, named
--                    WINDOW with FIRST_VALUE and LAG.
-- Caveats            The gap mixes two things: how many women are employed and in which roles;
--                    it is not "equal pay for equal work". Workforce = employees and workers,
--                    permanent and other. A group figure is shown only for 5 companies or more.

-- result: gender_by_sector_group
with years as (
    select
        count(distinct fiscal_year_label) as n_years,
        min(fiscal_year_label) as first_year,
        count(distinct fiscal_year_label) filter (where pay_equity_gap_pp is not null)
            as n_gap_years
    from fct_company_year
),

balanced_companies as (
    select
        company_year.isin,
        count(company_year.female_workforce_pct) = years.n_years as in_workforce_panel,
        count(company_year.pay_equity_gap_pp) = years.n_gap_years as in_gap_panel
    from fct_company_year as company_year
    cross join years
    group by company_year.isin, years.n_years, years.n_gap_years, years.first_year
    having
        count(*) = years.n_years
        and not bool_or(
            company_year.has_comparability_break
            and company_year.fiscal_year_label > years.first_year
        )
),

panels as (
    select
        'all companies' as panel,
        isin,
        sector_group,
        fiscal_year_label,
        headcount_female,
        headcount_total,
        female_workforce_pct,
        pay_equity_gap_pp
    from fct_company_year
    union all
    select
        'balanced panel' as panel,
        company_year.isin,
        company_year.sector_group,
        company_year.fiscal_year_label,
        company_year.headcount_female,
        company_year.headcount_total,
        case when balanced_companies.in_workforce_panel then company_year.female_workforce_pct end
            as female_workforce_pct,
        case when balanced_companies.in_gap_panel then company_year.pay_equity_gap_pp end
            as pay_equity_gap_pp
    from fct_company_year as company_year
    inner join balanced_companies on company_year.isin = balanced_companies.isin
),

workforce as (
    select
        panel,
        sector_group,
        fiscal_year_label,
        count(distinct isin) as n_companies_workforce,
        100 * sum(headcount_female) / sum(headcount_total) as female_workforce_agg
    from panels
    where female_workforce_pct is not null
    group by panel, sector_group, fiscal_year_label
),

pay_gap as (
    select
        panel,
        sector_group,
        fiscal_year_label,
        count(distinct isin) as n_companies_gap,
        median(pay_equity_gap_pp) as pay_equity_gap_median
    from panels
    where pay_equity_gap_pp is not null
    group by panel, sector_group, fiscal_year_label
),

combined as (
    select
        workforce.panel,
        workforce.sector_group,
        workforce.fiscal_year_label,
        workforce.n_companies_workforce,
        coalesce(pay_gap.n_companies_gap, 0) as n_companies_gap,
        case when workforce.n_companies_workforce >= 5 then workforce.female_workforce_agg end
            as female_workforce_agg,
        case when pay_gap.n_companies_gap >= 5 then pay_gap.pay_equity_gap_median end
            as pay_equity_gap_median
    from workforce
    left join pay_gap
        on
            workforce.panel = pay_gap.panel
            and workforce.sector_group = pay_gap.sector_group
            and workforce.fiscal_year_label = pay_gap.fiscal_year_label
)

select
    panel,
    sector_group,
    fiscal_year_label,
    n_companies_workforce,
    round(female_workforce_agg, 1) as female_workforce_agg_pct,
    round(female_workforce_agg - first_value(female_workforce_agg) over since_first, 1)
        as workforce_change_vs_first_year_pp,
    n_companies_gap,
    round(pay_equity_gap_median, 1) as pay_equity_gap_median_pp,
    round(pay_equity_gap_median - lag(pay_equity_gap_median) over since_first, 1)
        as gap_change_vs_previous_year_pp
from combined
window since_first as (partition by panel, sector_group order by fiscal_year_label)
order by sector_group, panel, fiscal_year_label;

-- result: pay_gap_narrowing
-- The balanced panel of the first result (filed in every year, no comparability break, a gap in
-- every year the wage share exists): first against latest year with a wage share.
with years as (
    select
        count(distinct fiscal_year_label) as n_years,
        min(fiscal_year_label) as first_year
    from fct_company_year
),

gap_years as (
    select
        min(fiscal_year_label) as first_gap_year,
        max(fiscal_year_label) as latest_gap_year,
        count(distinct fiscal_year_label) as n_gap_years
    from fct_company_year
    where pay_equity_gap_pp is not null
),

balanced as (
    select
        company_year.isin,
        any_value(company_year.sector_group) as sector_group,
        max(
            case
                when company_year.fiscal_year_label = gap_years.first_gap_year
                    then company_year.pay_equity_gap_pp
            end
        ) as gap_first,
        max(
            case
                when company_year.fiscal_year_label = gap_years.latest_gap_year
                    then company_year.pay_equity_gap_pp
            end
        ) as gap_latest
    from fct_company_year as company_year
    cross join gap_years
    cross join years
    group by company_year.isin, gap_years.n_gap_years, years.n_years, years.first_year
    having
        count(*) = years.n_years
        and count(company_year.pay_equity_gap_pp) = gap_years.n_gap_years
        and not bool_or(
            company_year.has_comparability_break
            and company_year.fiscal_year_label > years.first_year
        )
),

with_total as (
    select
        sector_group,
        gap_first,
        gap_latest
    from balanced
    union all
    select
        'All sector groups' as sector_group,
        gap_first,
        gap_latest
    from balanced
)

select
    sector_group,
    count(*) as n_companies,
    case when count(*) >= 5 then round(median(gap_first), 1) end as gap_median_first_year_pp,
    case when count(*) >= 5 then round(median(gap_latest), 1) end as gap_median_latest_year_pp,
    -- a gap is narrower when it is closer to zero (a move of 0.5 points or less is no move)
    count(*) filter (where abs(gap_latest) - abs(gap_first) < -0.5) as n_moved_closer_to_zero,
    count(*) filter (where abs(gap_latest) - abs(gap_first) > 0.5) as n_moved_away_from_zero,
    count(*) filter (where abs(abs(gap_latest) - abs(gap_first)) <= 0.5) as n_unchanged,
    round(100.0 * count(*) filter (where abs(gap_latest) - abs(gap_first) < -0.5) / count(*), 1)
        as share_moved_closer_pct
from with_total
group by sector_group
order by sector_group;
