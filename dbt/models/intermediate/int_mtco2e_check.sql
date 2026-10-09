-- Plausibility check for reading MtCO2e as metric tonnes (x1), one row per filing that files
-- Scope 1/2 in MtCO2e. Scope 1+2 intensity (tCO2e per rupee crore of corrected turnover) is
-- compared with the same company in its other years and with its industry peers (NIFTY 50
-- industry). If MtCO2e really meant megatonnes, intensity would be ~10^6 x too LOW here.
-- Peer medians need at least 3 other companies in the same industry and fiscal year.
--   is_implausible     more than 100x away from either reference (any direction)
--   likely_megatonnes  at least 10^4 x BELOW a reference: probably filed in megatonnes.
--                      Reported, NOT corrected (the agreed rule is Mt = metric tonnes).

with metrics as (
    select * from {{ ref('int_metric_values') }}
    where period_role = 'CY' and dimension_key = '' and is_latest_filing_for_value
),

industry as (
    select
        symbol,
        industry
    from {{ ref('stg_universe') }}
),

per_filing as (
    select
        filing_id,
        symbol,
        fiscal_year_label,
        sum(value_std) filter (where metric_id in ('ghg_scope1_tco2e', 'ghg_scope2_tco2e'))
            as scope12_tco2e,
        max(value_std) filter (where metric_id = 'turnover_inr') as turnover_inr,
        bool_or(unit_label = 'MtCO2e') filter (
            where metric_id in ('ghg_scope1_tco2e', 'ghg_scope2_tco2e')
        ) as files_mtco2e
    from metrics
    group by filing_id, symbol, fiscal_year_label
),

intensity as (
    select
        per_filing.*,
        coalesce(industry.industry, 'Not in NIFTY 50 list') as industry,
        per_filing.scope12_tco2e / nullif(per_filing.turnover_inr / 1e7, 0)
            as intensity_tco2e_per_inr_cr
    from per_filing
    left join industry on per_filing.symbol = industry.symbol
),

compared as (
    select
        this.*,
        (
            select median(other.intensity_tco2e_per_inr_cr)
            from intensity as other
            where other.symbol = this.symbol and other.filing_id != this.filing_id
        ) as company_other_years_median,
        (
            select
                case
                    when count(distinct peer.symbol) >= 3
                        then median(peer.intensity_tco2e_per_inr_cr)
                end
            from intensity as peer
            where
                peer.industry = this.industry
                and peer.symbol != this.symbol
                and peer.fiscal_year_label = this.fiscal_year_label
        ) as industry_peer_median
    from intensity as this
),

ratios as (
    select
        *,
        intensity_tco2e_per_inr_cr / nullif(company_other_years_median, 0) as ratio_to_company,
        intensity_tco2e_per_inr_cr / nullif(industry_peer_median, 0) as ratio_to_peers
    from compared
)

select
    filing_id,
    symbol,
    fiscal_year_label,
    industry,
    scope12_tco2e,
    turnover_inr,
    intensity_tco2e_per_inr_cr,
    company_other_years_median,
    industry_peer_median,
    ratio_to_company,
    ratio_to_peers,
    coalesce(abs(log10(ratio_to_company)) > 2 or abs(log10(ratio_to_peers)) > 2, false)
        as is_implausible,
    coalesce(ratio_to_company <= 1e-4 or ratio_to_peers <= 1e-4, false) as likely_megatonnes
from ratios
where files_mtco2e
