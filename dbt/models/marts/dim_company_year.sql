-- One row per company (ISIN) and financial year, from the latest filing of that year: reporting
-- period, boundary, size, assurance and structural-break flag. The grain every yearly fact
-- joins to. Size band = tercile of turnover within the sector group and year; for Financials
-- total headcount is used because a bank's "turnover" is not comparable.

with filings as (
    select
        company_names.isin,
        company_names.fiscal_year_label,
        company_names.filing_id,
        company_names.symbol,
        company_names.taxonomy_version,
        filings.period_start,
        filings.period_end,
        filings.period_months,
        filings.is_non_standard_period
    from {{ ref('int_company_names') }} as company_names
    inner join {{ ref('stg_filings') }} as filings on company_names.filing_id = filings.filing_id
),

current_values as (
    select *
    from {{ ref('int_metric_values') }}
    where period_role in ('CY', 'INSTANT_CY') and is_latest_filing_for_value
),

turnover as (
    select
        isin,
        fiscal_year_label,
        max(value_std) as turnover_inr
    from current_values
    where metric_id = 'turnover_inr' and dimension_key = ''
    group by isin, fiscal_year_label
),

-- the "Employees" and "Workers" totals already add up permanent and other-than-permanent staff
headcount as (
    select
        isin,
        fiscal_year_label,
        sum(value_std) as total_headcount
    from current_values
    where
        metric_id = 'headcount'
        and (
            dimension_key like '%=EmployeesMember|GenderAxis=GenderMember'
            or dimension_key like '%=WorkersMember|GenderAxis=GenderMember'
        )
    group by isin, fiscal_year_label
),

text_metrics as (
    select
        isin,
        fiscal_year_label,
        max(case when metric_id = 'reporting_boundary' then value_text end) as boundary_filed,
        max(case when metric_id = 'brsr_core_assurance_status' then value_text end)
            as assurance_filed
    from current_values
    where metric_id in ('reporting_boundary', 'brsr_core_assurance_status') and dimension_key = ''
    group by isin, fiscal_year_label
),

breaks as (
    select
        isin,
        affected_fiscal_year_label as fiscal_year_label,
        count(*) as n_events
    from {{ ref('corporate_events') }}
    where comparability_break
    group by isin, affected_fiscal_year_label
),

joined as (
    select
        filings.*,
        dim_company.display_name,
        dim_company.peer_group,
        dim_company.sector_group,
        dim_company.ranking_group,
        dim_company.peer_group_sort,
        dim_company.sector_group_sort,
        case
            when lower(text_metrics.boundary_filed) like 'consolidated%' then 'consolidated'
            when lower(text_metrics.boundary_filed) like 'standalone%' then 'standalone'
        end as reporting_boundary,
        12.0 / nullif(filings.period_months, 0) as annualisation_factor,
        turnover.turnover_inr,
        headcount.total_headcount,
        case
            when lower(text_metrics.assurance_filed) like '%assurance%' then 'assured'
            when lower(text_metrics.assurance_filed) like '%assessment%' then 'assessed'
            else coalesce(lower(text_metrics.assurance_filed), 'not disclosed')
        end as brsr_core_assurance_status,
        breaks.isin is not null as has_comparability_break,
        -- Financials are sized by headcount, everyone else by turnover
        dim_company.sector_group = 'Financials' as sized_by_headcount,
        case
            when dim_company.sector_group = 'Financials' then headcount.total_headcount
            else turnover.turnover_inr
        end as size_metric
    from filings
    inner join {{ ref('dim_company') }} as dim_company on filings.isin = dim_company.isin
    left join turnover
        on filings.isin = turnover.isin and filings.fiscal_year_label = turnover.fiscal_year_label
    left join headcount
        on filings.isin = headcount.isin and filings.fiscal_year_label = headcount.fiscal_year_label
    left join text_metrics
        on
            filings.isin = text_metrics.isin
            and filings.fiscal_year_label = text_metrics.fiscal_year_label
    left join breaks
        on filings.isin = breaks.isin and filings.fiscal_year_label = breaks.fiscal_year_label
),

banded as (
    select
        *,
        ntile(3) over (
            partition by sector_group, fiscal_year_label, size_metric is null
            order by size_metric, isin
        ) as size_tercile
    from joined
)

select
    isin,
    fiscal_year_label,
    filing_id,
    symbol,
    display_name,
    peer_group,
    sector_group,
    ranking_group,
    peer_group_sort,
    sector_group_sort,
    reporting_boundary,
    period_start,
    period_end,
    period_months,
    is_non_standard_period,
    annualisation_factor,
    taxonomy_version,
    turnover_inr,
    total_headcount,
    brsr_core_assurance_status,
    has_comparability_break,
    case
        when size_metric is null then null
        when size_tercile = 3 then 'Large'
        when size_tercile = 2 then 'Mid'
        else 'Small'
    end as size_band,
    case when sized_by_headcount then 'total_headcount' else 'turnover_inr' end as size_band_basis
from banded
