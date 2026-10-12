-- Time spine required by MetricFlow: one row per day from the first comparative year in the data
-- (FY2020-21) to the end of FY2026-27. The semantic layer only uses whole financial years (the
-- time dimension is the year-end date, 31 March), but MetricFlow needs a daily spine to exist.

select cast(spine.date_day as date) as date_day
from generate_series(date '2020-04-01', date '2027-03-31', interval 1 day) as spine (date_day)
