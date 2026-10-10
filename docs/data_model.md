# Data model

Two views of the same warehouse: the **gold star schema** (what reports and Power BI read) and the
identity layer underneath it. Built by dbt on DuckDB; column-level documentation and enforced
contracts are in `dbt/models/marts/_marts.yml`.

## Gold star schema

```mermaid
erDiagram
    dim_company ||--o{ fct_company_year : "isin"
    dim_company_year ||--|| fct_company_year : "isin + fiscal_year_label"
    dim_fiscal_year ||--o{ fct_company_year : "fiscal_year_label"
    dim_company ||--o{ fct_esg_value : "isin"
    dim_metric ||--o{ fct_esg_value : "metric_id"
    dim_fiscal_year ||--o{ fct_esg_value : "value_fiscal_year_label"
    dim_company ||--o{ fct_restatement : "isin"
    dim_metric ||--o{ fct_restatement : "metric_id"
    dim_company ||--o{ fct_company_kpi_percentile : "isin"
    fct_company_year ||--o{ fct_company_kpi_percentile : "isin + fiscal_year_label"
    fct_company_year }o--o{ fct_peer_benchmark : "ranking_group + fiscal_year_label"
    dim_company ||--o{ bridge_company_year_assurer : "isin"
    dim_assurer ||--o{ bridge_company_year_assurer : "assurer_key"
    dim_company ||--o{ dim_company_history : "isin"

    fct_esg_value {
        string isin FK
        string metric_id FK
        string value_fiscal_year_label FK
        string dimension_key
        string source_filing_id
        double value_std
        bool is_latest_value
        string source_citation
    }
    fct_company_year {
        string isin FK
        string fiscal_year_label FK
        double ghg_intensity_tco2e_per_cr
        double renewable_share_pct
        double pay_equity_gap_pp
        string ranking_group
    }
    fct_peer_benchmark {
        string ranking_group
        string fiscal_year_label
        string kpi_name
        double median_value
        int n_companies
    }
    fct_company_kpi_percentile {
        string isin FK
        string fiscal_year_label
        string kpi_name
        double percentile_in_group
    }
    fct_restatement {
        string isin FK
        string metric_id FK
        string value_fiscal_year_label
        string restating_filing_id
        double original_value
        double restated_value
        string classification
    }
    dim_company {
        string isin PK
        string peer_group
        string sector_group
    }
    dim_metric {
        string metric_id PK
        string unit_type
        string direction
    }
    dim_assurer {
        string assurer_key PK
        string assurer_name
    }
```

### Grains

| Table | Grain | Key |
|---|---|---|
| `fct_esg_value` | company x metric x year of the value x breakdown x source filing | `isin`, `metric_id`, `value_fiscal_year_label`, `dimension_key`, `source_filing_id` |
| `fct_company_year` | company x financial year (wide, KPIs) | `isin`, `fiscal_year_label` |
| `fct_peer_benchmark` | ranking group x financial year x KPI | `ranking_group`, `fiscal_year_label`, `kpi_name` |
| `fct_company_kpi_percentile` | company x financial year x KPI | `isin`, `fiscal_year_label`, `kpi_name` |
| `fct_restatement` | company x metric x breakdown x year restated x restating filing | `isin`, `metric_id`, `dimension_key`, `value_fiscal_year_label`, `restating_filing_id` |
| `rpt_restatement_summary` | level (overall / metric / peer group / company) x key | `level`, `group_key` |
| `dim_metric` | one per catalogue metric | `metric_id` |
| `dim_assurer` | one per assurance provider (variants merged) | `assurer_key` |
| `bridge_company_year_assurer` | company-year x assurer | `isin`, `fiscal_year_label`, `assurer_key` |

Every `dim_` and `fct_` model has an enforced dbt contract. Gold tables carry no links to the
exchange: `source_citation` is plain text (company, report, year, filing date).

### Which value is "the" value

`fct_esg_value.is_latest_value` marks, for each company, metric, year and breakdown, the
current-year value from the latest revision of the filing for that year. Prior-year comparatives
(PY, PY2) are kept for the restatement tracker but are never latest. Restatement logic:
[restatement_method.md](restatement_method.md); KPI formulas: [kpi_definitions.md](kpi_definitions.md).

## Identity layer

How the company and time dimensions relate to each other and to the metric values.

```mermaid
erDiagram
    dim_company ||--o{ dim_company_history : "isin"
    dim_company ||--o{ dim_company_year : "isin"
    dim_fiscal_year ||--o{ dim_company_year : "fiscal_year_label"
    dim_company_year ||--o{ int_yoy_anomalies : "isin + fiscal_year_label"
    dim_company_year ||--o{ int_metric_values : "isin + fiscal_year_label"
    dim_company ||--o{ corporate_events : "isin"
    dim_fiscal_year ||--o{ corporate_events : "affected_fiscal_year_label"
    peer_groups ||--|| dim_company : "symbol"
    company_attributes ||--|| dim_company : "symbol"
    metric_materiality }o--|| int_metric_values : "peer_group + metric_id"
    metric_disclosure_requirement ||--o{ int_metric_values : "metric_id"

    dim_company {
        string isin PK
        string current_name
        string display_name
        string peer_group
        string sector_group
        string ranking_group
        string nic_primary_code
        bool is_conglomerate
        string ownership_type
        string business_group
    }
    dim_company_history {
        string isin FK
        string company_name
        string symbol
        string valid_from_fy
        string valid_to_fy
        bool is_current
    }
    dim_company_year {
        string isin FK
        string fiscal_year_label FK
        string filing_id
        string reporting_boundary
        int period_months
        float annualisation_factor
        float turnover_inr
        float total_headcount
        string size_band
        bool boundary_changed_vs_prior
        bool has_comparability_break
        string comparability_break_reason
    }
    dim_fiscal_year {
        string fiscal_year_label PK
        int fy_sort
        bool is_brsr_core_year
        bool assurance_fields_available
    }
    int_metric_values {
        string isin FK
        string fiscal_year_label FK
        string metric_id
        float value_std
        string period_role
    }
```

## Grain and keys

| Table | Grain | Key |
|---|---|---|
| `dim_company` | one row per company | `isin` |
| `dim_company_history` | one row per run of years under the same name and symbol | `isin`, `valid_from_fy` |
| `dim_company_year` | one row per company and financial year (latest filing) | `isin`, `fiscal_year_label` |
| `dim_fiscal_year` (seed) | one row per financial year | `fiscal_year_label` |
| `int_metric_values` | one row per metric value (company, year, period role, breakdown) | `fact_id` |
| `int_yoy_anomalies` | one row per company-year and metric with a YoY move above 40% | `isin`, `fiscal_year_label`, `metric` |
| `int_metric_values_enriched` | same as `int_metric_values`, plus peer group and `is_material` | `fact_id` |

## How a value finds its context

1. A metric value carries `isin` and `fiscal_year_label` (the filing year; `value_fiscal_year_label`
   is the year the value itself belongs to, which differs for prior-year comparatives).
2. Join `dim_company_year` on `isin` + `fiscal_year_label` for the period, boundary, size band and
   break flag of that filing.
3. Join `dim_company` on `isin` for names, peer group, ranking group, NIC sector, ownership.
4. Join `metric_materiality` on `peer_group` + `metric_id` to know whether to rank it, and
   `metric_disclosure_requirement` on `metric_id` to know whether it was required that year.
5. `dim_company_history` is only needed to show the name a company had in a given year.

## Seeds that need human verification

`nic_sector_map` and `nic_code_corrections` (`verified_by` empty). `corporate_events`,
`company_attributes`, `peer_groups` and `metric_disclosure_requirement` are verified by the project owner.
