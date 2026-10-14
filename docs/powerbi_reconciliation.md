# Power BI reconciliation

Week 12. How we know the Power BI measures give the semantic layer's numbers, and the six
figures to check by hand in Power BI Desktop. Every value here is calculated (an intensity, a
share, a median or a count); no filed value is shown ([publication_policy.md](publication_policy.md)).

## What the scripts check

Power BI cannot be run from a script, so `scripts/reconcile_bi.py` computes six measures in
pandas with **the same formula as their DAX** (`scripts/build_powerbi.py`), on **the same
Parquet files** Power BI loads (`exports/local`), grouped through `dim_company` exactly as the
model's relationships do. Each figure is compared with `mf query` on the semantic layer.

| Power BI measure | Semantic-layer metric | Grouped by | Figures | Result |
|---|---|---|---|---|
| GHG intensity (whole group) | `ghg_intensity_agg` | sector group x year | 12 | equal |
| GHG intensity (typical company) | `ghg_intensity_median` | sector group x year | 12 | equal |
| Renewable share (whole group, %) | `renewable_share_agg` | peer group x year | 36 | equal |
| DQS median | `dqs_median` | sector group x year | 12 | equal |
| Grade A share (%) | `dqs_grade_a_share` | sector group x year | 12 | equal |
| Material restatement share (%) | `material_restatement_share` | year | 3 | equal |

87 figures, largest difference 5.7e-14 (build of 2026-10-14). The public model's group measures
read `rpt_public_group_metrics` directly; all 71 figures that table shows for these six
metrics are equal to the local formulas too. `tests/test_bi.py` runs both checks.

Not checked by the script, and the reason for the hand checklist below: whether Power BI
itself evaluates the DAX as written (filter context, relationships, blanks). TMDL structure
*is* checked: `scripts/check_tmdl.ps1` parses both models with Power BI Desktop's own library.

Run it yourself:

```powershell
.\scripts\dev.ps1 bi-export          # exports, then the workbook
.\scripts\dev.ps1 semantic           # if mf complains about a catalog (dbt parse on the real warehouse)
.venv\Scripts\python.exe scripts\reconcile_bi.py
```

## Checklist for Power BI Desktop (local model)

The pages themselves are built in the public model; its own numbers to check are at the end of
[powerbi_build_guide.md](powerbi_build_guide.md). The local model is opened only for these six.

Open `powerbi\esg_lens_local\esg_lens_local.pbip`, set the `ExportFolder` parameter (see
[powerbi_build_guide.md](powerbi_build_guide.md), "Before you start"), refresh, then put each
measure on a **Card** and set the filters with slicers on `dim_fiscal_year[fiscal_year_label]`
and `dim_company[sector_group]` or `dim_company[peer_group]`. Clear every other filter first.

| # | Measure | Filters | Expected | Done |
|---|---|---|---|---|
| 1 | Companies in selection | Year = FY2025-26 | **51** | - [ ] |
| 2 | GHG intensity (whole group) | Year = FY2025-26, sector group = Asset-heavy | **248.81** | - [ ] |
| 3 | GHG intensity (typical company) | Year = FY2025-26, sector group = Asset-heavy | **11.40** | - [ ] |
| 4 | Renewable share (whole group, %) | Year = FY2025-26, peer group = IT services | **68.1** | - [ ] |
| 5 | DQS median | Year = FY2024-25, no other filter | **85.65** | - [ ] |
| 6 | Material restatement share (%) | Year = FY2023-24 | **5.7** | - [ ] |

If a card shows a different number:

- **Several years selected?** Every expected value is for one year. A median over several years
  mixes years and is not what the semantic layer reports.
- **Sector or peer group from the wrong table?** Use `dim_company`, not a fact table's own
  column (the values are the same, but a slicer on a fact column does not filter the other
  facts).
- **Number 6 blank?** FY2025-26 has no restatement figures yet (no later report); pick FY2023-24.
- **Still off?** Compare the measure's DAX with `powerbi\esg_lens_local_measures.dax`; a
  hand edit in Desktop may have changed it.

The same figures in the **public model** (`esg_lens_public.pbip`): put a slicer on
`rpt_public_group_metrics[group_type]` and one on `[group_value]`, and select one year.
`GHG intensity, whole group` with group type `sector_group`, group `Asset-heavy`, FY2025-26
must show 248.81 as well, and `Disclosure Quality Score, typical company` with group type
`all`, FY2024-25 must show 85.65. A group with fewer than 5 companies (for example ranking
group Automobiles in FY2023-24) must show a blank card and `Withheld note` = "n<5: fewer than 5
companies".

The expected values are recomputed by `tests/test_bi.py` from the current export; the test
fails when this page is out of date.

## Excel

`esg_lens_public.xlsx` is opened in Excel by `scripts/check_excel.ps1`, recalculated in full
and scanned for errors: 0 error cells in 1,165 formulas. The Peer Benchmark sheet is then run
for every company with a GHG or water intensity in FY2024-25 and FY2025-26 (rank and percentile
equal to `fct_company_kpi_percentile`, peer median equal to `rpt_public_group_metrics`), and
every cell of the Sector Summary for every year is compared with `rpt_public_group_metrics`
(withheld cells must read "n<5" or "not yet observable").
