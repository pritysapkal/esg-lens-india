-- Q9. Restatements: how often does last year's number change, and in whose favour?
--
-- Business question  What share of the figures that can be compared with the next year's
--                    report are restated materially - by year and by metric - and how many of
--                    those restatements make the company's trend look better?
-- Stakeholder        Auditor, assurance provider or analyst who builds time series from BRSR.
-- Method             A pair = the value first filed for year Y and the comparative for Y in the
--                    report for Y+1. Material = changed by more than 5% (and more than 1
--                    percentage point for a percentage, at least 2 units for a count). Suspected
--                    scale errors and pairs whose unit had to be taken from the later report are
--                    not compared. "Flatters the trend" = the restated earlier value makes the
--                    change to the next year look better (a higher earlier value for a
--                    lower-is-better metric, and the reverse). The latest year is left out: its
--                    next report does not exist yet, so "no restatements" there would be wrong.
-- SQL techniques     Conditional aggregation with FILTER, NULLIF against division by zero,
--                    UNION ALL total row, scalar subquery for the latest year, QUALIFY with
--                    ROW_NUMBER for a top-10.
-- Caveats            A restatement is a difference between two filings, not a finding of
--                    wrongdoing; correcting a figure is good practice. FY2022-23 is noisy
--                    (inferred units). Flattering restatements can have honest causes (a changed
--                    emission factor, a wider boundary). Metrics without a direction cannot
--                    flatter and are left out of that share.

-- result: restatements_by_year
with observable as (
    select restatement.*
    from fct_restatement as restatement
    where
        restatement.value_fiscal_year_label
        < (select max(company_year.fiscal_year_label) from fct_company_year as company_year)
),

with_total as (
    select
        value_fiscal_year_label,
        is_compared,
        classification,
        flatters_trend,
        isin
    from observable
    union all
    select
        'All years' as value_fiscal_year_label,
        is_compared,
        classification,
        flatters_trend,
        isin
    from observable
)

select
    value_fiscal_year_label as year_of_the_value,
    count(*) filter (where is_compared) as n_pairs_compared,
    count(*) filter (where classification = 'material') as n_material,
    round(
        100.0 * count(*) filter (where classification = 'material')
        / nullif(count(*) filter (where is_compared), 0),
        2
    ) as material_share_pct,
    count(distinct isin) filter (where classification = 'material')
        as n_companies_with_material,
    count(*) filter (where classification = 'material' and flatters_trend is not null)
        as n_material_with_direction,
    count(*) filter (where classification = 'material' and flatters_trend) as n_flattering,
    round(
        100.0 * count(*) filter (where classification = 'material' and flatters_trend)
        / nullif(
            count(*) filter (where classification = 'material' and flatters_trend is not null), 0
        ),
        1
    ) as flattering_share_of_material_pct,
    count(*) filter (where classification = 'suspected_scale_error') as n_suspected_scale_errors
from with_total
group by value_fiscal_year_label
order by value_fiscal_year_label;

-- result: restatements_by_metric_top10
with observable as (
    select restatement.*
    from fct_restatement as restatement
    where
        restatement.value_fiscal_year_label
        < (select max(company_year.fiscal_year_label) from fct_company_year as company_year)
),

by_metric as (
    select
        metric_id,
        count(*) filter (where is_compared) as n_pairs_compared,
        count(*) filter (where classification = 'material') as n_material,
        count(distinct isin) filter (where classification = 'material')
            as n_companies_with_material,
        count(*) filter (where classification = 'material' and flatters_trend is not null)
            as n_material_with_direction,
        count(*) filter (where classification = 'material' and flatters_trend) as n_flattering
    from observable
    group by metric_id
)

select
    metric_id,
    n_pairs_compared,
    n_material,
    round(100.0 * n_material / nullif(n_pairs_compared, 0), 1) as material_share_pct,
    n_companies_with_material,
    n_flattering,
    round(100.0 * n_flattering / nullif(n_material_with_direction, 0), 1)
        as flattering_share_of_material_pct
from by_metric
where n_material > 0
qualify row_number() over (order by n_material desc, metric_id asc) <= 10
order by n_material desc, metric_id asc;
