-- The four weights of the Disclosure Quality Score (seed dqs_weights) must add up to 1, and all
-- four components must have a weight. Rows returned are violations.
select
    sum(weight) as total_weight,
    count(*) as n_components
from {{ ref('dqs_weights') }}
having abs(sum(weight) - 1) > 1e-9 or count(*) != 4
