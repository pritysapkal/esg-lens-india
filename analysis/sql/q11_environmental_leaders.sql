-- Q11. All-round environmental leaders: who is in the top quartile on several things at once?
--
-- Business question  Which companies are in the top quartile of their peers on at least three
--                    of six environmental KPIs in the latest year: GHG, energy, water and waste
--                    intensity, renewable share of energy, and waste recovery rate?
-- Stakeholder        Sustainable-fund manager looking for breadth, not one headline number.
-- Method             Percentile of each company within its ranking group (its peer group when
--                    that has 5 or more companies, otherwise its sector group), direction-aware:
--                    100 = best. Top quartile = percentile of 75 or more. Only KPIs that are
--                    ranked for the group count, so the number of chances differs by company;
--                    both the number of top-quartile KPIs and the number of ranked KPIs are
--                    shown.
-- SQL techniques     Scalar subquery for the latest year, filtered aggregation, STRING_AGG with
--                    ORDER BY and FILTER, HAVING, join to the dimension for names.
-- Caveats            None of the six KPIs is ranked for Financials (not material there), so no
--                    financial company can qualify; IT services are ranked on three of them
--                    only. The list is about companies with a physical footprint.
--                    A waste recovery rate above 100% is not ranked. Per rupee of turnover, a
--                    high-margin business looks cleaner than a low-margin one. The percentile
--                    places a company among 5 to 12 peers: "top quartile" can mean first or
--                    second of five.

-- result: top_quartile_on_three_or_more
with latest_year as (
    select max(fiscal_year_label) as fiscal_year_label
    from fct_company_year
),

environmental as (
    select
        percentile.isin,
        percentile.ranking_group,
        percentile.fiscal_year_label,
        percentile.kpi_name,
        percentile.percentile_in_group
    from fct_company_kpi_percentile as percentile
    inner join latest_year on percentile.fiscal_year_label = latest_year.fiscal_year_label
    where
        percentile.kpi_name in (
            'ghg_intensity_tco2e_per_cr',
            'energy_intensity_gj_per_cr',
            'water_intensity_kl_per_cr',
            'waste_intensity_t_per_cr',
            'renewable_share_pct',
            'waste_recovery_rate_pct'
        )
        and percentile.percentile_in_group is not null
),

per_company as (
    select
        isin,
        ranking_group,
        fiscal_year_label,
        count(*) as n_kpis_ranked,
        count(*) filter (where percentile_in_group >= 75) as n_kpis_top_quartile,
        string_agg(kpi_name, ', ' order by kpi_name) filter (where percentile_in_group >= 75)
            as top_quartile_kpis,
        round(median(percentile_in_group), 1) as median_percentile
    from environmental
    group by isin, ranking_group, fiscal_year_label
    having count(*) filter (where percentile_in_group >= 75) >= 3
)

select
    per_company.fiscal_year_label,
    per_company.ranking_group,
    company.display_name,
    per_company.n_kpis_top_quartile,
    per_company.n_kpis_ranked,
    per_company.median_percentile,
    per_company.top_quartile_kpis
from per_company
inner join dim_company as company on per_company.isin = company.isin
order by per_company.n_kpis_top_quartile desc, per_company.median_percentile desc;

-- result: leaders_by_ranking_group
-- How many companies of each ranked group qualify: shows where breadth is common and where rare.
with latest_year as (
    select max(fiscal_year_label) as fiscal_year_label
    from fct_company_year
),

per_company as (
    select
        percentile.isin,
        percentile.ranking_group,
        count(*) filter (where percentile.percentile_in_group >= 75) as n_kpis_top_quartile
    from fct_company_kpi_percentile as percentile
    inner join latest_year on percentile.fiscal_year_label = latest_year.fiscal_year_label
    where
        percentile.kpi_name in (
            'ghg_intensity_tco2e_per_cr',
            'energy_intensity_gj_per_cr',
            'water_intensity_kl_per_cr',
            'waste_intensity_t_per_cr',
            'renewable_share_pct',
            'waste_recovery_rate_pct'
        )
        and percentile.percentile_in_group is not null
    group by percentile.isin, percentile.ranking_group
)

select
    ranking_group,
    count(*) as n_companies_ranked,
    count(*) filter (where n_kpis_top_quartile >= 3) as n_all_round_leaders,
    count(*) filter (where n_kpis_top_quartile = 0) as n_with_no_top_quartile
from per_company
group by ranking_group
order by ranking_group;
