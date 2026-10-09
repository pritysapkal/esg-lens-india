-- Turnover per filing (current year), as filed and corrected for scale errors.
-- Rule (docs/business_rules.md): a turnover below 10^9 INR (Rs 100 crore) is not plausible for a
-- NIFTY 50 company, so it was filed in crore, million or lakh. The scale is chosen by comparing
-- with the company's other years that look right (>= 10^9): the candidate that lands closest
-- (log distance) wins. Crore (x10^7) is the default when there is nothing to compare with.
-- evidence_ratio = (filed Scope 1+2) / turnover_raw / (filed Scope 1+2 intensity per rupee):
-- if the filer computed the intensity with turnover in rupees, it is ~ the scale factor.

{{ config(materialized='table') }}

with facts as (
    select * from {{ ref('int_period_role') }}
    where period_role = 'CY' and not has_dimensions
),

turnover as (
    select
        filing_id,
        symbol,
        fiscal_year_label,
        value_num as turnover_raw
    from facts
    where concept = 'Turnover' and value_num is not null
),

-- Filed (not normalised) values, only to test the filer's own arithmetic.
ghg as (
    select
        filing_id,
        sum(value_num) filter (
            where concept in ('TotalScope1Emissions', 'TotalScope2Emissions')
        ) as scope12_filed,
        max(value_num) filter (
            where concept in (
                'TotalScope1AndScope2EmissionsIntensityPerRupeeOfTurnover',
                'TotalScope1AndScope2EmissionsPerRupeeOfTurnover'
            )
        ) as intensity_filed
    from facts
    group by filing_id
),

reference as (
    select
        turnover.filing_id,
        median(other.turnover_raw) as reference_inr,
        count(other.filing_id) as n_reference_years
    from turnover
    left join turnover as other
        on
            turnover.symbol = other.symbol
            and turnover.filing_id != other.filing_id
            and other.turnover_raw >= 1e9
    group by turnover.filing_id
),

scales as (
    select
        10000000.0 as scale,
        'crore' as scale_name
    union all
    select
        1000000.0 as scale,
        'million' as scale_name
    union all
    select
        100000.0 as scale,
        'lakh' as scale_name
),

candidates as (
    select
        turnover.filing_id,
        scales.scale,
        scales.scale_name,
        abs(log10(turnover.turnover_raw * scales.scale / reference.reference_inr)) as fit
    from turnover
    inner join reference on turnover.filing_id = reference.filing_id
    cross join scales
    where
        turnover.turnover_raw < 1e9
        and turnover.turnover_raw > 0
        and reference.reference_inr is not null
),

best as (
    select
        filing_id,
        arg_min(scale, fit) as scale,
        arg_min(scale_name, fit) as scale_name,
        min(fit) as fit
    from candidates
    group by filing_id
),

decided as (
    select
        turnover.*,
        reference.reference_inr,
        reference.n_reference_years,
        ghg.scope12_filed / nullif(turnover.turnover_raw, 0) / nullif(ghg.intensity_filed, 0)
            as evidence_ratio,
        case
            when turnover.turnover_raw >= 1e9 then 1.0
            else coalesce(best.scale, 10000000.0)
        end as scale,
        case
            when turnover.turnover_raw >= 1e9 then 'rupees'
            else coalesce(best.scale_name, 'crore')
        end as scale_name,
        best.fit
    from turnover
    inner join reference on turnover.filing_id = reference.filing_id
    left join ghg on turnover.filing_id = ghg.filing_id
    left join best on turnover.filing_id = best.filing_id
),

with_ratio as (
    select
        *,
        {{ round_sig("turnover_raw * scale") }} as turnover_inr,
        scale != 1 as scale_applied,
        turnover_raw * scale / nullif(reference_inr, 0) as ratio_to_other_years
    from decided
)

select
    filing_id,
    symbol,
    fiscal_year_label,
    turnover_raw,
    turnover_inr,
    scale_applied,
    scale,
    scale_name,
    reference_inr,
    n_reference_years,
    ratio_to_other_years,
    evidence_ratio,
    case
        when not scale_applied then null
        else
            'turnover ' || turnover_raw || ' < 1e9 INR: read as ' || scale_name || ' (x'
            || cast(cast(scale as bigint) as varchar) || ')'
            || case
                when
                    reference_inr is null
                    then '; no other plausible year to compare (default crore)'
                else
                    '; ' || round(ratio_to_other_years, 2)
                    || 'x the median of the other ' || n_reference_years || ' year(s)'
            end
            || case
                when scale_name != 'crore' then '; x1e7 rule rejected by other years' else ''
            end
    end as correction_reason,
    case
        -- not corrected: high unless the value is far from the company's other years
        when
            not scale_applied
            and (reference_inr is null or ratio_to_other_years between 1.0 / 3 and 3)
            then 'high'
        when not scale_applied and ratio_to_other_years between 0.1 and 10 then 'medium'
        when not scale_applied then 'low'
        -- corrected and compared with other years (fit = |log10(ratio)|)
        when fit is not null and fit <= log10(1.5) then 'high'
        when fit is not null and fit <= log10(3) then 'medium'
        -- weak fit, but the filer's own intensity arithmetic points to the same scale
        when fit is not null and abs(log10(evidence_ratio) - log10(scale)) <= 0.5 then 'medium'
        when fit is not null then 'low'
        -- corrected without comparison: rely on the filer's intensity arithmetic
        when evidence_ratio between 10000000.0 / 3 and 10000000.0 * 3 then 'medium'
        else 'low'
    end as confidence
from with_ratio
