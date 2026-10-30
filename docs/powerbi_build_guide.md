# Power BI build guide: five pages

Week 12. The data model and every measure are ready; the pages are yours to build. This guide
takes you through five pages, one step at a time. Each page lists its purpose, the fields and
measures to use, a suggested visual, the numbers to check, and one point to make in an
interview.

**All five pages are built in the public project.** It reads only the public models, so every
page can be shown in a screenshot or the demo video.

| Project | Reads | Use it for |
|---|---|---|
| `powerbi\esg_lens_public\esg_lens_public.pbip` | `exports\public` (the six `rpt_public_*` models only) | **the five pages** |
| `powerbi\esg_lens_local\esg_lens_local.pbip` | `exports\local` (raw filed values included) | only the six-number check in [powerbi_reconciliation.md](powerbi_reconciliation.md), and your own analysis; never shown, never screenshotted |

## Before you start (once)

1. Run `.\scripts\dev.ps1 dbt-build` and then `.\scripts\dev.ps1 bi-export`. This writes the
   Parquet files to `exports\local` and `exports\public`.
2. Open the local project first and tick the six numbers in
   [powerbi_reconciliation.md](powerbi_reconciliation.md): that proves the measures and the
   relationships work in your Power BI. Then close it and open
   `powerbi\esg_lens_public\esg_lens_public.pbip` (Power BI Desktop 2.158 or later; PBIP
   format with a TMDL model).
3. **Set the folder.** Home > Transform data > Edit parameters > `ExportFolder` = the full path
   of `exports\public`, without a backslash at the end, for example
   `D:\work\esg-lens-india\exports\public`. Close & Apply, then Refresh.
4. **Do not commit your path.** Saving writes it into `expressions.tmdl`. Before a commit run
   `git checkout -- powerbi/*/*.SemanticModel/definition/expressions.tmdl`, or once:
   `git update-index --skip-worktree` on those two files. A test fails if a drive path such as
   `D:\` is in `powerbi/`.

If a project does not open: create a blank report, open **TMDL view**, paste the whole of
`powerbi\esg_lens_public.tmdl-script.tmdl` and press Apply, then do step 3. Single measures are
also in `powerbi\esg_lens_public_measures.dax`.

### How the public model is laid out

| Table | One row is | Used on |
|---|---|---|
| `dim_company` | a company (key `isin`), built from `rpt_public_company_year` | every page (slicers) |
| `dim_fiscal_year` | a financial year, sorted by `fy_start_year` | every page (slicers) |
| `rpt_public_company_year` | a company in a year: computed intensities and shares | 5 |
| `rpt_public_disclosure_quality` | a company in a year: Disclosure Quality Score | 4, 5 |
| `rpt_public_group_metrics` | a group type x group x year: published group figures | 1, 2, 4 |
| `rpt_public_concentration` | a company in a year: rank and share of all emissions (no tonnes) | 3 |
| `rpt_public_company_percentile` | a company x KPI x year: percentile, rank, ranked or not and why | 5 |
| `rpt_public_restatement_summary` | a restatement class count by level | 4 (optional) |

- Star schema: `dim_company` and `dim_fiscal_year` filter the company tables; every
  relationship runs one way. **Always slice by the dimensions.**
- All measures are in **`_Measures`**, in display folders: 1 Coverage, 2 Intensity and shares,
  3 Disclosure quality, 4 Restatements, 5 Data status and labels, 6 Concentration (shares),
  7 Company card. Hover over a measure to read its description.
- Implicit measures are switched off: dragging a column into a value well gives no sum. That is
  deliberate - a sum or average of an intensity is never a right answer.
- **Group figures** come from `rpt_public_group_metrics`, one row per group type, group and year.
  A group measure shows a value only when exactly one such row is selected: put slicers on
  `rpt_public_group_metrics[group_type]`, `rpt_public_group_metrics[group_value]` and
  `dim_fiscal_year[fiscal_year_label]`. It is blank when fewer than 5 companies stand behind
  it; always show `[Withheld note]` next to it. Nothing is recomputed from company rows.
- **Whole group** = all emissions over all turnover of the group (large companies weigh more);
  **typical company** = the median.

## Page 1 - Overview

**Purpose.** One screen that says what is covered and how the whole set looks in one year.

**Fields and measures.**

- Slicers: `dim_fiscal_year[fiscal_year_label]` (single select), with `[Year status]` in a
  small card under it; a filter `rpt_public_group_metrics[group_type]` = `all` on each group
  card (a visual filter: `page.json` is generated, see "After saving in Power BI Desktop").
- Cards: `[Companies reporting]`, `[GHG intensity, whole group]`,
  `[Disclosure Quality Score, typical company]`, `[Companies disclosing Scope 3 (%)]`,
  `[Renewable share of energy, whole group (%)]`, `[Figures materially restated (%)]` with
  `[Withheld note]` under it (FY2025-26 restatements are not yet observable).
- `[Top-5 share of emissions (%)]` as a further card links to page 3.
- A text box: what this is and what it is not (not an ESG rating, not investment advice).

**Visual.** A row of KPI cards across the top, the year slicer on the left.

**Check.** FY2025-26: `[Companies reporting]` = 51 (see the table at the end).

**Interview talking point.** "The cards look simple, but each one has a rule behind it: a
group figure is a ratio of sums or a median, never an average of ratios, and it is blank when
fewer than five companies stand behind it. The blank is a feature, and the card says why."

## Page 2 - Decarbonisation: whole group vs typical company

**Purpose.** Show that "is heavy industry decarbonising?" has two honest answers.

**Fields and measures.**

- Page filter: `rpt_public_group_metrics[group_type]` = `sector_group`.
- X axis: `dim_fiscal_year[fiscal_year_label]`; legend: `rpt_public_group_metrics[group_value]`.
- Values: `[GHG intensity, whole group]` (left chart) and `[GHG intensity, typical company]`
  (right chart). Tooltip: `[Companies with a ghg intensity]`, `[Withheld note]`.
- Ranking groups instead of sectors (group type `ranking_group`): add
  `[Ranking note: GHG intensity]` to the tooltip. For Financials it reads "not ranked for this
  group (not material)": the median is shown as a description, but companies are not ranked
  on GHG intensity there.
- **Balanced panel:** the public tables hold no panel figure. Put the Week 10 result in a text
  box: "Following the same 15 Asset-heavy companies, the whole group's intensity rose 3.7% from
  FY2022-23 to FY2025-26 while the typical company fell 38%" ([analysis_findings.md](analysis_findings.md), Q1).

**Visual.** Two line charts side by side, one line per sector group. Asset-heavy is about 50
times Asset-light: use small multiples or a log scale.

**Check.** FY2025-26, Asset-heavy: whole group 248.81, typical company 11.40.

**Interview talking point.** "The two lines differ by a factor of twenty for heavy industry,
and both are right: a few very carbon-heavy companies set the whole-group figure, the many
small ones set the median. The dashboard never averages company intensities, because that
number describes neither."

## Page 3 - Concentration (Pareto)

**Purpose.** Show that a handful of companies carry most of the emissions - in shares, never
tonnes.

**Fields and measures.**

- Slicer: `dim_fiscal_year[fiscal_year_label]` (single select).
- Axis: `dim_company[display_name]`, sorted by `[Emitter rank]` ascending (Sort axis > Emitter
  rank; or a Top N filter of 15 on `[Emitter rank]`).
- Columns: `[Share of total emissions (%)]`. Line: `[Cumulative share of emissions (%)]`.
- Cards: `[Top-5 share of emissions (%)]`, `[Top-10 share of emissions (%)]`,
  `[Companies for 80% of emissions]`.
- Colour the columns by `rpt_public_concentration[is_top_5]`.

**Visual.** Line and clustered column chart (Pareto) with a constant line at 80% on the
secondary axis; the three cards above it.

**Check.** FY2025-26: top-5 share 85.5, companies for 80% 5 (Week 10 Q2: 85.5% to 86.2% over
the four years).

**Interview talking point.** "Five companies are 85% of the emissions and ten are 98%. Any
average trend of this index is the trend of a power producer, two steel makers, a cement maker
and a refiner - so the other pages work with intensities and medians, and this one shows
shares, not tonnes."

## Page 4 - Disclosure quality and data trust

**Purpose.** How good and how trustworthy is the reporting: scores, restatements, and which
year is still provisional.

**Fields and measures.**

- Slicer: one year (scores are comparable within a year only); page filter group type
  `sector_group` (or `ranking_group`).
- Matrix rows `rpt_public_group_metrics[group_value]`; values
  `[Disclosure Quality Score, typical company]`, `[Disclosure Quality Score, average]`,
  `[Company-years graded A (%)]`, `[Voluntary depth, average]`,
  `[Companies with a Disclosure Quality Score]`, `[Figures materially restated (%)]`,
  `[Withheld note]`.
- Company table: `dim_company[display_name]` with the columns `dqs_total`, `dqs_grade`,
  `dqs_rank_in_group` and `dqs_reason_codes` of `rpt_public_disclosure_quality` (a table visual
  shows them as they are; no sum), plus `[Company: data status]`.
- Restatement classes from `rpt_public_restatement_summary`, levels `peer_group` and
  `overall` (the table has no `year` level): figures compared and the unchanged / minor /
  material shares, in a table. It has no year column, so it covers all years and ignores the
  year slicer.
- Provisional label in the title: "FY2025-26 is provisional: no later report has confirmed it
  yet", or a card with `[Company: data status]`.

**Visual.** Matrix of the scores by sector group; a table of every company, highest score
first; a table of restatement classes by peer group.

**Check.** FY2024-25, group type `all`: typical company score 85.65.

**Interview talking point.** "A score here is about how far the numbers can be trusted, not
whether they are good - the Week 11 test found no association with carbon intensity. And every
figure of the latest year carries a provisional label, because the next report may still
restate it."

## Page 5 - Company card

**Purpose.** One company on one screen, placed among its peers without exposing filed values.

**Fields and measures.**

- Slicers: `dim_company[display_name]` (single select) and one year.
- Cards: `[Company: GHG intensity]`, `[Peer median: GHG intensity]`, `[Company: DQS]`,
  `[Company: DQS grade]`, `[Company: DQS rank in group]`, `[Company: DQS percentile in group]`,
  `[Peer median: DQS]`, `[Company: renewable share (%)]`, `[Company: women in workforce (%)]`,
  `[Company: pay-equity gap (pp)]`, `[Company: data status]`.
- **Peer table:** rows `rpt_public_company_percentile[kpi_label]`; values
  `[Company: peer percentile]`, `[Company: rank in group]`, `[Company: companies in group]`,
  `[Company: ranking status]`, `[Company: KPI value (public KPIs)]`. The value stays empty for
  filed KPIs (a filed percentage is not public); the percentile and rank are shown for all.
- "Not material" shows as "not ranked for this group (not material)" in
  `[Company: ranking status]` - for example GHG intensity for a bank.

**Visual.** Cards in a grid at the top; a bar chart of `[Company: peer percentile]` by
`kpi_label` (0-100, 100 = best) with a constant line at 50; the peer table under it.

**Check.** Asian Paints, FY2024-25, GHG intensity row: percentile 57.1, rank 4.

**Interview talking point.** "The card never shows a filed tonne, rupee or filed percentage:
only our intensities, ranks, percentiles and scores, each with the peer median it should be
read against - and when a KPI is not ranked, it says why."

## Numbers to check in the public model

Recomputed from the public files by `tests/test_bi.py`; the test fails when this table is out
of date. Clear all other filters first.

| Page | Measure | Filters | Expected |
|---|---|---|---|
| 1 | Companies reporting | group type all, FY2025-26 | **51** |
| 2 | GHG intensity, whole group | group type sector_group, Asset-heavy, FY2025-26 | **248.81** |
| 2 | GHG intensity, typical company | group type sector_group, Asset-heavy, FY2025-26 | **11.40** |
| 3 | Top-5 share of emissions (%) | FY2025-26 | **85.5** |
| 3 | Companies for 80% of emissions | FY2025-26 | **5** |
| 4 | Disclosure Quality Score, typical company | group type all, FY2024-25 | **85.65** |
| 5 | Company: peer percentile | Asian Paints, FY2024-25, GHG intensity row | **57.1** |
| 5 | Company: rank in group | Asian Paints, FY2024-25, GHG intensity row | **4** |
| 5 | Ranking note: GHG intensity | group type ranking_group, Financials, FY2024-25 | **not ranked for this group (not material)** |

The last row still shows the descriptive median: `[GHG intensity, typical company]` for the
same selection is 0.79.

## Colour, accessibility and labels

- **Colour.** One colour per sector group, the same on every page (for example Asset-heavy
  dark blue, Asset-light teal, Financials orange). Use a colour-blind-safe palette (never red
  against green as the only difference) and never encode meaning by colour alone: add the label
  or an icon too. Keep text contrast at least 4.5:1.
- **Withheld and provisional.** Withheld = grey with the text "n<5" (`[Withheld note]`), never
  a zero. Provisional = the same colour as final but lighter or hatched, with "Provisional" in
  the title or the data label (`[Company: data status]`). A note on every page: "FY2025-26 is
  provisional: no later report has confirmed it yet."
- **Not ranked** = its own label (`[Company: ranking status]`, `[Ranking note: GHG intensity]`),
  never an empty bar that looks like a zero.
- **Accessibility.** A title and alt text on every visual (Format > General > Alt text) that
  says what it shows; a sensible tab order (View > Selection); text size 12 or more; no text
  inside images.
- **Units** in every title: "tCO2e per Rs crore", "%", "points (0-100)", "percentile (100 =
  best)".
- **Disclaimer** on every page: "The Disclosure Quality Score is not an ESG rating, and this is
  not investment advice."

## After saving in Power BI Desktop

Saving the project rewrites more than your pages. Before a commit, put the generated files
back and keep only what you built.

**What Desktop changes on save**

- `expressions.tmdl`: your `ExportFolder` path.
- The other `.tmdl` files: measures reformatted onto one line, `ref table` lines and
  annotations added. Same model, different text: `build_powerbi.py --check` and the tests that
  read the measures fail on it.
- `report.json`: a newer `$schema` (3.3.0 with Desktop 2.159) and a `resourcePackages` block.
- `.pbip`, `definition.pbir`, `definition.pbism`, `version.json`, `pages.json`, `page.json`:
  formatting only (the final newline goes).
- New, untracked: `.platform` files (Fabric Git metadata) and `.pbi/` folders (local
  settings and caches, ignored by `.gitignore`).

**Keep**

- `powerbi/*/*.Report/definition/pages/*/visuals/`: the visuals you built.
- `tests/fixtures/pbir_schemas/`: the official schemas the report test validates against.

**Put back**

1. With the warehouse built, run `python scripts/build_powerbi.py`. It rewrites every
   generated file of both projects (model, `.pbip`, `definition.pbir`, `report.json`,
   `pages.json`, `page.json`) and leaves `visuals/` alone. It also resets `ExportFolder` to the
   `SET-ME` placeholder. Without the warehouse, the same thing is
   `git checkout -- powerbi/*/*.SemanticModel powerbi/*/*.pbip powerbi/*/*.Report/definition.pbir powerbi/*/*.Report/definition/report.json powerbi/*/*.Report/definition/version.json powerbi/*/*.Report/definition/pages/pages.json powerbi/*/*.Report/definition/pages/*/page.json`
   (that drops a measure you added in the generator but have not committed yet: use the
   script then).
2. Check: `python scripts/build_powerbi.py --check` and `pytest tests/test_bi.py`.
3. `git status`: only `visuals/` files (and any new fixture schema) should be left to commit.

**Rules that follow from this**

- `page.json` is generated: a page-level filter, page background or edit-interactions setting
  made in Desktop is lost. Put filters on the visuals (Filters pane > "Filters on this visual").
- Desktop can rewrite a visual with the newest `visualContainer` schema it knows (Desktop
  2.159 ships 2.14.0, not yet published; the committed visuals use 2.13.0). If the test reports a `$schema` it cannot resolve, download that version and
  what it references from
  [microsoft/json-schemas](https://github.com/microsoft/json-schemas/tree/main/fabric/item/report/definition)
  into `tests/fixtures/pbir_schemas/` (same folder layout), or set the visual files back to the
  newest version that is there.

**Set `ExportFolder` again** after putting the files back, before you next open the project:
Home > Transform data > Edit parameters (step 3 of "Before you start"), then Refresh.

## Publishing

Dashboards are published **only as screenshots or a video of the public project**. The `.pbip`
files, `exports\local` and the local project are never shared. Before a screenshot: no filed
absolute value on the page (tonnes, GJ, kl, rupees, headcounts), no filed percentage, no link
to the exchange, and the provisional label visible where the latest year is shown.
