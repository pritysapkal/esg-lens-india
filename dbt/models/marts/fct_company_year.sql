-- One wide row per company and financial year: reported values and KPIs we derive ourselves from
-- the latest current-year values (fct_esg_value.is_latest_value) and dim_company_year.
-- Rules: turnover is the corrected turnover (turnover_cr = turnover_inr / 1e7); any division by
-- zero or by a missing denominator gives null; intensities are null when turnover is null.
-- Percent columns are on a 0-100 scale. Headcount basis: employees + workers, permanent and
-- other than permanent (the "Employees" and "Workers" totals). Quantities are as filed;
-- *_annualised columns are filled only for years that are not 12 months (x 12 / months).
-- Values are the best available ones (fct_esg_value.best_value_std): a current-year value that
-- is a suspected scale error is replaced by the comparative from the next report, counted in
-- n_values_replaced. Implausible zeros (e.g. 0% of wages to women with women on the payroll)
-- are set to empty and named in kpi_flags; so are other things a reader should know.

{% set no_dim = {
    'ghg_s1_tco2e': 'ghg_scope1_tco2e',
    'ghg_s2_tco2e': 'ghg_scope2_tco2e',
    'ghg_s3_tco2e': 'ghg_scope3_tco2e',
    'ghg_intensity_filed_per_cr': 'ghg_intensity_filed_tco2e_per_inr_cr',
    'energy_total_gj': 'energy_total_gj',
    'energy_renewable_gj': 'energy_renewable_gj',
    'energy_intensity_filed_gj_per_cr': 'energy_intensity_filed_gj_per_inr_cr',
    'water_withdrawal_kl': 'water_withdrawal_kl',
    'water_consumption_kl': 'water_consumption_kl',
    'water_intensity_filed_kl_per_cr': 'water_intensity_filed_kl_per_inr_cr',
    'waste_generated_t': 'waste_generated_t',
    'waste_recovered_t': 'waste_recovered_t',
    'waste_disposed_t': 'waste_disposed_t',
    'female_wage_share_pct': 'female_wage_share_pct',
    'female_board_pct': 'female_board_pct',
    'posh_complaints_pct_female': 'posh_complaints_pct_female',
    'posh_upheld_count': 'posh_complaints_upheld_count',
    'wellbeing_cost_pct_revenue': 'wellbeing_cost_pct_revenue',
    'msme_sourcing_pct': 'msme_sourcing_pct',
    'days_payable_filed': 'days_payable',
    'rpt_purchases_pct': 'rpt_purchases_pct',
    'rpt_sales_pct': 'rpt_sales_pct',
    'data_breaches_count': 'data_breaches_count',
} %}

{% set annualised = [
    'ghg_s1_tco2e', 'ghg_s2_tco2e', 'ghg_s12_tco2e', 'ghg_s3_tco2e',
    'energy_total_gj', 'energy_renewable_gj', 'water_withdrawal_kl', 'water_consumption_kl',
    'waste_generated_t', 'waste_recovered_t', 'waste_disposed_t', 'turnover_inr',
] %}

with latest as (
    select
        isin,
        value_fiscal_year_label as fiscal_year_label,
        metric_id,
        dimension_key,
        best_value_std as value_std,
        best_value_source,
        coalesce(value_text, raw_value) as value_text
    from {{ ref('fct_esg_value') }}
    where is_latest_value
),

reported as (
    select
        isin,
        fiscal_year_label,
        count(*) filter (where best_value_source = 'replaced_by_later_comparative')
            as n_values_replaced,
        {%- for column, metric in no_dim.items() %}
            max(case when metric_id = '{{ metric }}' and dimension_key = '' then value_std end)
                as {{ column }},
        {%- endfor %}
        max(
            case
                when metric_id = 'brsr_core_assurance_type' and dimension_key = '' then value_text
            end
        )
            as assurance_type,
        max(
            case
                when
                    metric_id = 'ltifr'
                    and dimension_key = 'EmployeesAndWorkersAxis=EmployeesMember'
                    then value_std
            end
        ) as ltifr_employees,
        max(
            case
                when metric_id = 'ltifr' and dimension_key = 'EmployeesAndWorkersAxis=WorkersMember'
                    then value_std
            end
        ) as ltifr_workers,
        max(
            case
                when
                    metric_id = 'recordable_injuries_count'
                    and dimension_key = 'EmployeesAndWorkersAxis=EmployeesMember'
                    then value_std
            end
        ) as recordable_employees,
        max(
            case
                when
                    metric_id = 'recordable_injuries_count'
                    and dimension_key = 'EmployeesAndWorkersAxis=WorkersMember'
                    then value_std
            end
        ) as recordable_workers,
        max(
            case
                when
                    metric_id = 'fatalities_count'
                    and dimension_key = 'EmployeesAndWorkersAxis=EmployeesMember'
                    then value_std
            end
        ) as fatalities_employees,
        max(
            case
                when
                    metric_id = 'fatalities_count'
                    and dimension_key = 'EmployeesAndWorkersAxis=WorkersMember'
                    then value_std
            end
        ) as fatalities_workers,
        sum(
            case
                when
                    metric_id = 'headcount'
                    and (
                        dimension_key like '%=EmployeesMember|GenderAxis=FemaleMember'
                        or dimension_key like '%=WorkersMember|GenderAxis=FemaleMember'
                    )
                    then value_std
            end
        ) as headcount_female,
        max(
            case
                when
                    metric_id = 'attrition_rate_pct'
                    and dimension_key like 'GenderAxis=FemaleMember|%=PermanentEmployeesMember'
                    then value_std
            end
        ) as attrition_female_pct,
        max(
            case
                when
                    metric_id = 'attrition_rate_pct'
                    and dimension_key like 'GenderAxis=MaleMember|%=PermanentEmployeesMember'
                    then value_std
            end
        ) as attrition_male_pct
    from latest
    group by isin, fiscal_year_label
),

company_year as (
    select * from {{ ref('dim_company_year') }}
),

company as (
    select
        isin,
        ownership_type,
        business_group
    from {{ ref('dim_company') }}
),

base as (
    select
        company_year.isin,
        company_year.fiscal_year_label,
        company_year.filing_id,
        company_year.symbol,
        company_year.display_name,
        company_year.peer_group,
        company_year.sector_group,
        company_year.ranking_group,
        company.ownership_type,
        company.business_group,
        company_year.size_band,
        company_year.size_band_basis,
        company_year.reporting_boundary,
        company_year.brsr_core_assurance_status,
        reported.assurance_type,
        company_year.has_comparability_break,
        company_year.comparability_break_reason,
        company_year.period_months,
        company_year.annualisation_factor,
        company_year.turnover_inr,
        company_year.turnover_inr / 1e7 as turnover_cr,
        company_year.total_headcount as headcount_total,
        cast(coalesce(reported.n_values_replaced, 0) as integer) as n_values_replaced,
        reported.headcount_female,
        reported.ghg_s1_tco2e,
        reported.ghg_s2_tco2e,
        reported.ghg_s3_tco2e,
        reported.ghg_intensity_filed_per_cr,
        reported.energy_total_gj,
        reported.energy_renewable_gj,
        reported.energy_intensity_filed_gj_per_cr,
        reported.water_withdrawal_kl,
        reported.water_consumption_kl,
        reported.water_intensity_filed_kl_per_cr,
        reported.waste_generated_t,
        reported.waste_recovered_t,
        reported.waste_disposed_t,
        reported.ltifr_employees,
        reported.ltifr_workers,
        reported.recordable_employees,
        reported.recordable_workers,
        reported.fatalities_employees,
        reported.fatalities_workers,
        reported.female_wage_share_pct,
        reported.female_board_pct,
        reported.attrition_female_pct,
        reported.attrition_male_pct,
        reported.posh_complaints_pct_female,
        reported.posh_upheld_count,
        reported.wellbeing_cost_pct_revenue,
        reported.msme_sourcing_pct,
        reported.rpt_purchases_pct,
        reported.rpt_sales_pct,
        reported.data_breaches_count,
        -- the filed payables days are not meaningful for lenders and insurers
        case
            when company_year.sector_group = 'Financials' then null
            else reported.days_payable_filed
        end as days_payable,
        case
            when reported.ghg_s1_tco2e is not null and reported.ghg_s2_tco2e is not null
                then reported.ghg_s1_tco2e + reported.ghg_s2_tco2e
        end as ghg_s12_tco2e
    from company_year
    left join reported
        on
            company_year.isin = reported.isin
            and company_year.fiscal_year_label = reported.fiscal_year_label
    left join company on company_year.isin = company.isin
),

zero_checks as (
    select
        *,
        coalesce(female_wage_share_pct = 0 and headcount_female > 0, false) as zero_wage_share,
        coalesce(
            energy_total_gj = 0 and turnover_cr > 0 and sector_group != 'Financials', false
        ) as zero_energy,
        coalesce(water_withdrawal_kl = 0 and sector_group != 'Financials', false) as zero_water,
        coalesce(headcount_total = 0, false) as zero_headcount
    from base
),

cleaned as (
    select
        * replace (
            case when zero_wage_share then null else female_wage_share_pct end
                as female_wage_share_pct,
            case when zero_energy then null else energy_total_gj end as energy_total_gj,
            case when zero_water then null else water_withdrawal_kl end as water_withdrawal_kl,
            case when zero_headcount then null else headcount_total end as headcount_total
        )
    from zero_checks
),

kpi as (
    select
        *,
        ghg_s3_tco2e is not null as scope3_disclosed,
        ghg_s12_tco2e / nullif(turnover_cr, 0) as ghg_intensity_tco2e_per_cr,
        energy_renewable_gj / nullif(energy_total_gj, 0) * 100 as renewable_share_pct,
        energy_total_gj / nullif(turnover_cr, 0) as energy_intensity_gj_per_cr,
        water_consumption_kl / nullif(turnover_cr, 0) as water_intensity_kl_per_cr,
        waste_recovered_t / nullif(waste_generated_t, 0) * 100 as waste_recovery_rate_pct,
        waste_generated_t / nullif(turnover_cr, 0) as waste_intensity_t_per_cr,
        (waste_generated_t - waste_recovered_t - waste_disposed_t)
        / nullif(waste_generated_t, 0) * 100 as waste_balance_gap_pct,
        case
            when recordable_employees is not null or recordable_workers is not null
                then coalesce(recordable_employees, 0) + coalesce(recordable_workers, 0)
        end as recordable_injuries_total,
        case
            when fatalities_employees is not null or fatalities_workers is not null
                then coalesce(fatalities_employees, 0) + coalesce(fatalities_workers, 0)
        end as fatalities_total,
        headcount_female / nullif(headcount_total, 0) * 100 as female_workforce_pct,
        attrition_female_pct - attrition_male_pct as attrition_gap_pp,
        data_breaches_count > 0 as any_data_breach
    from cleaned
),

final as (
    select
        *,
        fatalities_total > 0 as any_fatality,
        fatalities_total / nullif(headcount_total, 0) * 10000 as fatalities_per_10k_workforce,
        female_wage_share_pct - female_workforce_pct as pay_equity_gap_pp,
        ghg_intensity_filed_per_cr / nullif(ghg_intensity_tco2e_per_cr, 0)
            as ghg_intensity_filed_vs_computed_ratio,
        energy_intensity_filed_gj_per_cr / nullif(energy_intensity_gj_per_cr, 0)
            as energy_intensity_filed_vs_computed_ratio,
        water_intensity_filed_kl_per_cr / nullif(water_intensity_kl_per_cr, 0)
            as water_intensity_filed_vs_computed_ratio,
        nullif(
            concat_ws(
                '|',
                case when zero_wage_share then 'implausible_zero_female_wage_share' end,
                case when zero_energy then 'implausible_zero_energy_total' end,
                case when zero_water then 'implausible_zero_water_withdrawal' end,
                case when zero_headcount then 'implausible_zero_headcount' end,
                case when waste_recovery_rate_pct > 100 then 'waste_recovery_over_100' end,
                case when n_values_replaced > 0 then 'scale_error_values_replaced' end
            ),
            ''
        ) as kpi_flags
    from kpi
)

select
    isin,
    fiscal_year_label,
    filing_id,
    symbol,
    display_name,
    peer_group,
    sector_group,
    ranking_group,
    size_band,
    size_band_basis,
    ownership_type,
    business_group,
    reporting_boundary,
    brsr_core_assurance_status,
    assurance_type,
    has_comparability_break,
    comparability_break_reason,
    period_months,
    annualisation_factor,
    turnover_inr,
    turnover_cr,
    headcount_total,
    headcount_female,
    female_workforce_pct,
    female_wage_share_pct,
    pay_equity_gap_pp,
    female_board_pct,
    attrition_female_pct,
    attrition_male_pct,
    attrition_gap_pp,
    ghg_s1_tco2e,
    ghg_s2_tco2e,
    ghg_s12_tco2e,
    ghg_s3_tco2e,
    scope3_disclosed,
    ghg_intensity_tco2e_per_cr,
    ghg_intensity_filed_per_cr,
    ghg_intensity_filed_vs_computed_ratio,
    {{ intensity_basis('ghg_intensity_filed_vs_computed_ratio') }} as ghg_intensity_filed_basis,
    energy_total_gj,
    energy_renewable_gj,
    renewable_share_pct,
    energy_intensity_gj_per_cr,
    energy_intensity_filed_gj_per_cr,
    energy_intensity_filed_vs_computed_ratio,
    {{ intensity_basis('energy_intensity_filed_vs_computed_ratio') }}
        as energy_intensity_filed_basis,
    water_withdrawal_kl,
    water_consumption_kl,
    water_intensity_kl_per_cr,
    water_intensity_filed_kl_per_cr,
    water_intensity_filed_vs_computed_ratio,
    {{ intensity_basis('water_intensity_filed_vs_computed_ratio') }}
        as water_intensity_filed_basis,
    waste_generated_t,
    waste_recovered_t,
    waste_disposed_t,
    waste_recovery_rate_pct,
    waste_intensity_t_per_cr,
    waste_balance_gap_pct,
    ltifr_employees,
    ltifr_workers,
    recordable_injuries_total,
    fatalities_total,
    any_fatality,
    fatalities_per_10k_workforce,
    posh_complaints_pct_female,
    posh_upheld_count,
    wellbeing_cost_pct_revenue,
    msme_sourcing_pct,
    days_payable,
    rpt_purchases_pct,
    rpt_sales_pct,
    {% for column in annualised %}
        case
            when period_months != 12 then {{ column }} * annualisation_factor
        end as {{ column }}_annualised,
    {% endfor %}
    any_data_breach,
    n_values_replaced,
    kpi_flags
from final
