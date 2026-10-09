-- Which period each value belongs to, relative to its filing:
--   CY          duration ending on the filing's period end (the reporting year itself)
--   PY          duration ending the day before the filing's period starts (comparative year)
--   PY2         duration ending the day before the PY period starts (second comparative)
--   INSTANT_CY  point in time at the filing's period end
--   INSTANT_PY  point in time the day before the filing's period starts
--   OTHER       anything else (e.g. quarters)
-- Anchored on the filing's own period, so 15-month and calendar-year filings work: NESTLEIND
-- FY2023-24 runs 2023-01-01..2024-03-31, so its PY is calendar 2022 (ends 2022-12-31).
-- value_fiscal_year_label is the April-March financial year in which the value's period ENDS.

with facts as (
    select * from {{ ref('int_facts_with_context') }}
),

anchored as (
    select
        *,
        cast(filing_period_start - interval 1 day as date) as py_end
    from facts
),

-- PY2 ends the day before PY starts. Using PY's own start (not "PY end - 1 year") keeps it right
-- when the PY itself is a 15-month period (NESTLEIND FY2024-25: PY 2023-01..2024-03, PY2 = 2022).
with_py_start as (
    select
        *,
        min(case when period_type = 'duration' and end_date = py_end then start_date end)
            over (partition by filing_id) as py_start
    from anchored
)

-- all fact columns pass through, plus the period role
select
    * exclude (py_end, py_start),  -- noqa: AM04
    case
        when period_type = 'duration' and end_date = filing_period_end then 'CY'
        when period_type = 'duration' and end_date = py_end then 'PY'
        when
            period_type = 'duration'
            and end_date = cast(py_start - interval 1 day as date)
            then 'PY2'
        when period_type = 'instant' and instant_date = filing_period_end then 'INSTANT_CY'
        when period_type = 'instant' and instant_date = py_end then 'INSTANT_PY'
        else 'OTHER'
    end as period_role,
    coalesce(end_date, instant_date) as value_period_end,
    {{ fiscal_year_label('coalesce(end_date, instant_date)') }} as value_fiscal_year_label
from with_py_start
