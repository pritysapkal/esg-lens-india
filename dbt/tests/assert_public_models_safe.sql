-- Publication policy (docs/publication_policy.md): the public models hold only values we
-- calculate. Rows returned are violations. For each public model and the gold table it reads
-- (rpt_public_company_year <- fct_company_year, rpt_public_disclosure_quality <-
-- fct_disclosure_quality):
--  1. the public model has a numeric column the kpi_catalogue seed marks public_safe = false or
--     does not know for that gold table;
--  2. a public_safe KPI of the catalogue is missing from the public model;
--  3. a public model has a column named like a raw filed quantity (..._tco2e, ..._gj, ..._kl,
--     ..._t, turnover, headcount) or a raw restatement value / filing text.
-- The catalogue must also describe every numeric column of the two gold tables, and nothing else.
-- Only the company-level rows of the catalogue are meant here (metric_type = 'company_value').
-- Its other rows are the group metrics of the semantic layer; for rpt_public_group_metrics:
--  4. a numeric column is not a public_safe group metric of the catalogue (this also keeps out
--     the hidden sums of filed values, ..._num / ..._den), or a public group metric is missing;
--  5. a group statistic (ratio, median, average, share) is shown although fewer than 5 companies
--     stand behind it (its companies_metric of the catalogue).
-- For rpt_public_concentration and rpt_public_company_percentile (positions of one company):
--  6. a numeric column is not a public_safe public_position row of the catalogue for that
--     model, or such a row is missing from the model;
--  7. rpt_public_company_percentile shows kpi_value_public for a KPI that is not public_safe
--     (a filed value).

-- The column lists are read from information_schema, so tell dbt what must be built first:
-- depends_on: {{ ref('fct_company_year') }}
-- depends_on: {{ ref('rpt_public_company_year') }}
-- depends_on: {{ ref('fct_disclosure_quality') }}
-- depends_on: {{ ref('rpt_public_disclosure_quality') }}
-- depends_on: {{ ref('rpt_public_restatement_summary') }}
-- depends_on: {{ ref('rpt_public_group_metrics') }}
-- depends_on: {{ ref('rpt_public_concentration') }}
-- depends_on: {{ ref('rpt_public_company_percentile') }}

with model_pairs as (
    select
        pairs.public_model,
        pairs.source_model
    from (
        values
        ('rpt_public_company_year', 'fct_company_year'),
        ('rpt_public_disclosure_quality', 'fct_disclosure_quality')
    ) as pairs (public_model, source_model)
),

public_columns as (
    select
        table_name,
        column_name,
        data_type in ('DOUBLE', 'INTEGER', 'BIGINT', 'FLOAT', 'HUGEINT') as is_numeric
    from information_schema.columns
    where
        table_name in (
            'rpt_public_company_year', 'rpt_public_disclosure_quality',
            'rpt_public_restatement_summary', 'rpt_public_group_metrics',
            'rpt_public_concentration', 'rpt_public_company_percentile'
        )
),

fact_columns as (
    select
        table_name,
        column_name
    from information_schema.columns
    where
        table_name in ('fct_company_year', 'fct_disclosure_quality')
        and data_type in ('DOUBLE', 'INTEGER', 'BIGINT', 'FLOAT', 'HUGEINT')
),

catalogue as (
    select
        kpi_catalogue.kpi_name,
        kpi_catalogue.public_safe,
        kpi_catalogue.source_model,
        model_pairs.public_model
    from {{ ref('kpi_catalogue') }} as kpi_catalogue
    left join model_pairs on kpi_catalogue.source_model = model_pairs.source_model
    where kpi_catalogue.metric_type = 'company_value'
),

group_catalogue as (
    select
        kpi_name,
        public_safe,
        metric_type,
        companies_metric
    from {{ ref('kpi_catalogue') }}
    where metric_type not in ('company_value', 'public_position')
),

position_catalogue as (
    select
        kpi_name,
        public_safe,
        source_model
    from {{ ref('kpi_catalogue') }}
    where metric_type = 'public_position'
),

position_columns as (
    select
        table_name,
        column_name
    from public_columns
    where
        table_name in ('rpt_public_concentration', 'rpt_public_company_percentile')
        and is_numeric
),

group_columns as (
    select column_name
    from public_columns
    where table_name = 'rpt_public_group_metrics' and is_numeric
),

-- one row per figure that is shown (unpivot leaves out the empty cells)
group_cells as (
    unpivot (
        select
            group_type,
            group_value,
            fiscal_year_label,
            cast(
                columns(* exclude (group_type, group_value, fiscal_year_label, suppressed_reason))
                as double
            )
        from {{ ref('rpt_public_group_metrics') }}
    )
    on columns(* exclude (group_type, group_value, fiscal_year_label))
    into name metric_name value metric_value
)

select
    'not public_safe in kpi_catalogue: ' || public_columns.table_name || '.'
    || public_columns.column_name as problem
from public_columns
inner join model_pairs on public_columns.table_name = model_pairs.public_model
left join catalogue
    on
        public_columns.column_name = catalogue.kpi_name
        and public_columns.table_name = catalogue.public_model
where public_columns.is_numeric and not coalesce(catalogue.public_safe, false)

union all

select
    'public_safe KPI missing from ' || coalesce(catalogue.public_model, 'a public model') || ': '
    || catalogue.kpi_name as problem
from catalogue
left join public_columns
    on
        catalogue.kpi_name = public_columns.column_name
        and catalogue.public_model = public_columns.table_name
where catalogue.public_safe and public_columns.column_name is null

union all

select 'raw-value column in a public model: ' || table_name || '.' || column_name as problem
from public_columns
where
    regexp_matches(
        column_name, '(_tco2e|_gj|_kl|_t)(_annualised)?$|turnover|headcount|_num$|_den$'
    )
    or column_name in (
        'original_value', 'restated_value', 'abs_change', 'stated_reason', 'value_std',
        'best_value_std', 'raw_value', 'value_text', 'value_pct'
    )

union all

select
    fact_columns.table_name || ' numeric column not in catalogue: ' || fact_columns.column_name
        as problem
from fact_columns
left join catalogue
    on
        fact_columns.column_name = catalogue.kpi_name
        and fact_columns.table_name = catalogue.source_model
where catalogue.kpi_name is null

union all

select
    'catalogue row not a numeric ' || catalogue.source_model || ' column: ' || catalogue.kpi_name
        as problem
from catalogue
left join fact_columns
    on
        catalogue.kpi_name = fact_columns.column_name
        and catalogue.source_model = fact_columns.table_name
where fact_columns.column_name is null

union all

select
    'rpt_public_group_metrics column is not a public_safe group metric: '
    || group_columns.column_name as problem
from group_columns
left join group_catalogue on group_columns.column_name = group_catalogue.kpi_name
where not coalesce(group_catalogue.public_safe, false)

union all

select
    'public_safe group metric missing from rpt_public_group_metrics: ' || group_catalogue.kpi_name
        as problem
from group_catalogue
left join group_columns on group_catalogue.kpi_name = group_columns.column_name
where group_catalogue.public_safe and group_columns.column_name is null

union all

select 'group statistic without a companies_metric: ' || kpi_name as problem
from group_catalogue
where
    public_safe
    and metric_type in ('ratio_of_sums', 'median', 'average', 'share')
    and companies_metric is null

union all

select
    'statistic shown for fewer than 5 companies: ' || statistic.metric_name || ' ('
    || statistic.group_type || ' / ' || statistic.group_value || ' / '
    || statistic.fiscal_year_label || ')' as problem
from group_cells as statistic
inner join group_catalogue on statistic.metric_name = group_catalogue.kpi_name
left join group_cells as companies
    on
        group_catalogue.companies_metric = companies.metric_name
        and statistic.group_type = companies.group_type
        and statistic.group_value = companies.group_value
        and statistic.fiscal_year_label = companies.fiscal_year_label
where
    group_catalogue.metric_type in ('ratio_of_sums', 'median', 'average', 'share')
    and coalesce(companies.metric_value, 0) < 5

union all

select
    'not a public_safe public_position of the catalogue: ' || position_columns.table_name || '.'
    || position_columns.column_name as problem
from position_columns
left join position_catalogue
    on
        position_columns.column_name = position_catalogue.kpi_name
        and position_columns.table_name = position_catalogue.source_model
where not coalesce(position_catalogue.public_safe, false)

union all

select
    'public_position missing from ' || position_catalogue.source_model || ': '
    || position_catalogue.kpi_name as problem
from position_catalogue
left join position_columns
    on
        position_catalogue.kpi_name = position_columns.column_name
        and position_catalogue.source_model = position_columns.table_name
where position_catalogue.public_safe and position_columns.column_name is null

union all

select distinct
    'filed value shown in rpt_public_company_percentile: '
    || percentile.kpi_name as problem
from {{ ref('rpt_public_company_percentile') }} as percentile
left join {{ ref('kpi_catalogue') }} as catalogue
    on
        percentile.kpi_name = catalogue.kpi_name
        and catalogue.metric_type = 'company_value'
where percentile.kpi_value_public is not null and not coalesce(catalogue.public_safe, false)
