-- Gold integrity: (1) exactly one official current value (is_latest_value) per company, metric,
-- value year and breakdown that has a current-year value; (2) no percentile without a group of
-- at least 5 companies; (3) every company-level KPI of the kpi_catalogue seed is a column of its
-- source_model (fct_company_year or fct_disclosure_quality).
-- depends_on: {{ ref('fct_disclosure_quality') }}
with latest_counts as (
    select
        isin,
        metric_id,
        value_fiscal_year_label,
        dimension_key,
        count(*) filter (where is_latest_value) as n_latest,
        count(*) filter (where is_current_year_value) as n_current
    from {{ ref('fct_esg_value') }}
    group by isin, metric_id, value_fiscal_year_label, dimension_key
)

select
    'not exactly one latest value: ' || isin || ' ' || metric_id || ' '
    || value_fiscal_year_label as problem
from latest_counts
where n_current > 0 and n_latest != 1

union all

select 'percentile with group_n < 5: ' || isin || ' ' || kpi_name as problem
from {{ ref('fct_company_kpi_percentile') }}
where percentile_in_group is not null and group_n < 5

union all

select
    'kpi_catalogue entry is not a column of ' || kpi_catalogue.source_model || ': '
    || kpi_catalogue.kpi_name as problem
from {{ ref('kpi_catalogue') }} as kpi_catalogue
left join information_schema.columns as table_columns
    on
        kpi_catalogue.kpi_name = table_columns.column_name
        and kpi_catalogue.source_model = table_columns.table_name
where kpi_catalogue.metric_type = 'company_value' and table_columns.column_name is null
