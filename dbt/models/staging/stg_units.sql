-- One row per XBRL unit: measures without namespace prefixes and simple unit flags.

with units as (
    select * from {{ source('brsr_raw', 'units') }}
),

cleaned as (
    select
        filing_id,
        unit_id,
        reporting_year_label,
        numerator_measures as numerator_measures_qname,
        denominator_measures as denominator_measures_qname,
        list_transform(numerator_measures, lambda m: {{ strip_ns_prefix('m') }})
            as numerator_measures,
        list_transform(denominator_measures, lambda m: {{ strip_ns_prefix('m') }})
            as denominator_measures
    from units
)

select
    filing_id,
    unit_id,
    reporting_year_label,
    numerator_measures,
    denominator_measures,
    array_to_string(numerator_measures, '*')
    || case
        when len(denominator_measures) > 0
            then '/' || array_to_string(denominator_measures, '*')
        else ''
    end as unit_label,
    len(denominator_measures) > 0 as is_ratio_unit,
    numerator_measures = ['pure'] and len(denominator_measures) = 0 as is_pure,
    numerator_measures_qname,
    denominator_measures_qname
from cleaned
