-- Publication policy (docs/publication_policy.md): the public models hold only values we
-- calculate. Rows returned are violations.
--  1. rpt_public_company_year has a numeric column the kpi_catalogue seed marks public_safe = false
--     or does not know;
--  2. a public_safe KPI of the catalogue is missing from rpt_public_company_year;
--  3. a public model has a column named like a raw filed quantity (..._tco2e, ..._gj, ..._kl,
--     ..._t, turnover, headcount) or a raw restatement value / filing text.
-- The catalogue must also describe every numeric column of fct_company_year, and nothing else.

-- The column lists are read from information_schema, so tell dbt what must be built first:
-- depends_on: {{ ref('fct_company_year') }}
-- depends_on: {{ ref('rpt_public_company_year') }}
-- depends_on: {{ ref('rpt_public_restatement_summary') }}

with public_columns as (
    select
        table_name,
        column_name,
        data_type in ('DOUBLE', 'INTEGER', 'BIGINT', 'FLOAT', 'HUGEINT') as is_numeric
    from information_schema.columns
    where table_name in ('rpt_public_company_year', 'rpt_public_restatement_summary')
),

fact_columns as (
    select column_name
    from information_schema.columns
    where
        table_name = 'fct_company_year'
        and data_type in ('DOUBLE', 'INTEGER', 'BIGINT', 'FLOAT', 'HUGEINT')
),

catalogue as (
    select
        kpi_name,
        public_safe
    from {{ ref('kpi_catalogue') }}
)

select 'not public_safe in kpi_catalogue: ' || public_columns.column_name as problem
from public_columns
left join catalogue on public_columns.column_name = catalogue.kpi_name
where
    public_columns.table_name = 'rpt_public_company_year'
    and public_columns.is_numeric
    and not coalesce(catalogue.public_safe, false)

union all

select 'public_safe KPI missing from rpt_public_company_year: ' || catalogue.kpi_name as problem
from catalogue
left join public_columns
    on
        catalogue.kpi_name = public_columns.column_name
        and public_columns.table_name = 'rpt_public_company_year'
where catalogue.public_safe and public_columns.column_name is null

union all

select 'raw-value column in a public model: ' || table_name || '.' || column_name as problem
from public_columns
where
    regexp_matches(column_name, '(_tco2e|_gj|_kl|_t)(_annualised)?$|turnover|headcount')
    or column_name in (
        'original_value', 'restated_value', 'abs_change', 'stated_reason', 'value_std',
        'best_value_std', 'raw_value', 'value_text', 'value_pct'
    )

union all

select 'fct_company_year numeric column not in catalogue: ' || fact_columns.column_name as problem
from fact_columns
left join catalogue on fact_columns.column_name = catalogue.kpi_name
where catalogue.kpi_name is null

union all

select 'catalogue row not a numeric fct_company_year column: ' || catalogue.kpi_name as problem
from catalogue
left join fact_columns on catalogue.kpi_name = fact_columns.column_name
where fact_columns.column_name is null
