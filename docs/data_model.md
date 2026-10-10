# Data model - identity layer

How the company and time dimensions relate to each other and to the metric values. Built by dbt
on DuckDB; details of each column are in `dbt/models/marts/_marts.yml`.

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
