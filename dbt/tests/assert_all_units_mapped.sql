-- Every catalogue value with a number has a unit conversion (seeds/unit_normalisation.csv).

select
    fact_id,
    symbol,
    metric_id,
    unit_label_effective,
    unit_std
from {{ ref('int_values_normalised') }}
where normalisation_flag like '%unit_not_in_map%'
