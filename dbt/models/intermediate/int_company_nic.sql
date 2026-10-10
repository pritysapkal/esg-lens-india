-- NIC sector rows from the BRSR "products or services sold accounting for 90% of turnover" table:
-- one row per filing and table row. The NIC code, its turnover share and its description are
-- three facts in the same context (same dimension member), so they are paired on that member.
-- Codes are digits only, with the approved fixes from the nic_code_corrections seed applied.
-- Shares are as filed (a fraction of total turnover); filings are not forced to sum to 1.

with facts as (
    select * from {{ ref('int_facts_with_context') }}
    where
        concept in (
            'NICCodeOfProductOrServiceSoldByTheEntity',
            'PercentageOfTotalTurnoverForProductOrServiceSold',
            'ProductOrServiceSoldByTheEntity'
        )
        and start_date = filing_period_start
        and end_date = filing_period_end
),

paired as (
    select
        filing_id,
        dimension_key,
        any_value(symbol) as symbol,
        any_value(isin) as isin,
        any_value(fiscal_year_label) as fiscal_year_label,
        max(case when concept = 'NICCodeOfProductOrServiceSoldByTheEntity' then raw_value end)
            as nic_code_as_filed,
        max(
            case
                when concept = 'PercentageOfTotalTurnoverForProductOrServiceSold' then value_num
            end
        ) as turnover_share,
        max(case when concept = 'ProductOrServiceSoldByTheEntity' then raw_value end)
            as product_description
    from facts
    group by filing_id, dimension_key
),

digits as (
    select
        *,
        regexp_replace(nic_code_as_filed, '[^0-9]', '', 'g') as nic_code_digits
    from paired
),

corrected as (
    select
        digits.*,
        corrections.symbol is not null as is_code_corrected,
        corrections.reason as correction_reason,
        case
            when corrections.symbol is not null then nullif(corrections.nic_code_corrected, '')
            else digits.nic_code_digits
        end as nic_code_candidate
    from digits
    left join {{ ref('nic_code_corrections') }} as corrections
        on
            digits.symbol = corrections.symbol
            and digits.fiscal_year_label = corrections.fiscal_year_label
            and digits.nic_code_digits = corrections.nic_code_raw
),

classified as (
    select
        *,
        -- usable = at least a 2-digit division and not all zeros ("0" means no code)
        case
            when
                length(nic_code_candidate) >= 2
                and nic_code_candidate != repeat('0', length(nic_code_candidate))
                then nic_code_candidate
        end as nic_code
    from corrected
),

shared as (
    select
        *,
        left(nic_code, 2) as nic_division_2d,
        sum(turnover_share) over (partition by filing_id, nic_code) as nic_code_share
    from classified
)

select
    filing_id,
    symbol,
    isin,
    fiscal_year_label,
    dimension_key,
    nic_code_as_filed,
    nic_code,
    nic_division_2d,
    length(nic_code) as nic_code_length,
    is_code_corrected,
    correction_reason,
    turnover_share,
    product_description,
    nic_code_share,
    sum(turnover_share) over (partition by filing_id, nic_division_2d) as nic_division_share,
    sum(turnover_share) over (partition by filing_id) as filing_share_total,
    -- primary = the code with the highest share in the filing; ties -> lowest code
    coalesce(
        dense_rank() over (
            partition by filing_id, nic_code is not null
            order by nic_code_share desc, nic_code asc
        ) = 1
        and nic_code is not null,
        false
    ) as is_primary_in_filing
from shared
