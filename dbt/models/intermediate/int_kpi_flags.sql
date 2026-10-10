-- One row per company-year and KPI flag raised in fct_company_year (kpi_flags unpacked), with a
-- plain-English detail. Flags: implausible zeros that were set to empty, a waste recovery rate
-- above 100%, and values replaced by the later comparative. Input for the Disclosure Quality
-- Score (Week 8).

with flagged as (
    select
        isin,
        symbol,
        fiscal_year_label,
        headcount_female,
        waste_recovery_rate_pct,
        n_values_replaced,
        unnest(string_split(kpi_flags, '|')) as flag
    from {{ ref('fct_company_year') }}
    where kpi_flags is not null
)

select
    isin,
    symbol,
    fiscal_year_label,
    flag,
    case flag
        when 'implausible_zero_female_wage_share'
            then
                'wage share to women filed as 0 with '
                || cast(cast(headcount_female as bigint) as varchar)
                || ' women in the workforce; set to empty'
        when 'implausible_zero_energy_total'
            then 'total energy filed as 0 for a company with turnover; set to empty'
        when 'implausible_zero_water_withdrawal'
            then 'water withdrawal filed as 0 for a non-financial company; set to empty'
        when 'implausible_zero_headcount' then 'total headcount is 0; set to empty'
        when 'waste_recovery_over_100'
            then
                'waste recovered is '
                || cast(round(waste_recovery_rate_pct, 1) as varchar)
                || '% of waste generated (possible legacy waste); value kept, not ranked'
        when 'scale_error_values_replaced'
            then
                cast(n_values_replaced as varchar)
                || ' current-year value(s) replaced by the comparative from the next report'
    end as detail
from flagged
