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

-- The column lists are read from information_schema, so tell dbt what must be built first:
-- depends_on: {{ ref('fct_company_year') }}
-- depends_on: {{ ref('rpt_public_company_year') }}
-- depends_on: {{ ref('fct_disclosure_quality') }}
-- depends_on: {{ ref('rpt_public_disclosure_quality') }}
-- depends_on: {{ ref('rpt_public_restatement_summary') }}

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
            'rpt_public_restatement_summary'
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
    regexp_matches(column_name, '(_tco2e|_gj|_kl|_t)(_annualised)?$|turnover|headcount')
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
