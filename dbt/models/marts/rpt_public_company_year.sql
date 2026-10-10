-- PUBLIC view of the company-year KPIs: only values we calculate ourselves (intensities per Rs
-- crore, computed percentages, gaps, yes/no flags) plus names and groups. No value copied from a
-- filing is in this table: no quantity (emissions, energy, water, waste, turnover, headcount,
-- counts) and no filed percentage or rate either (those are public only as gaps, percentiles or
-- peer statistics).
-- Policy: docs/publication_policy.md. The column list must match the public_safe columns of the
-- kpi_catalogue seed; assert_public_models_safe checks it on every build.

select
    isin,
    symbol,
    display_name,
    fiscal_year_label,
    peer_group,
    sector_group,
    ranking_group,
    size_band,
    ownership_type,
    business_group,
    reporting_boundary,
    brsr_core_assurance_status,
    assurance_type,
    has_comparability_break,
    comparability_break_reason,
    period_months,
    annualisation_factor,
    female_workforce_pct,
    pay_equity_gap_pp,
    attrition_gap_pp,
    scope3_disclosed,
    ghg_intensity_tco2e_per_cr,
    ghg_intensity_filed_basis,
    renewable_share_pct,
    energy_intensity_gj_per_cr,
    energy_intensity_filed_basis,
    water_intensity_kl_per_cr,
    water_intensity_filed_basis,
    waste_recovery_rate_pct,
    waste_intensity_t_per_cr,
    waste_balance_gap_pct,
    any_fatality,
    fatalities_per_10k_workforce,
    any_data_breach,
    n_values_replaced,
    kpi_flags
from {{ ref('fct_company_year') }}
