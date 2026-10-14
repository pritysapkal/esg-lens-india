# Power BI build guide: five pages

Week 12. The data model and every measure are ready; the pages are yours to build. This guide
takes you through five pages, one step at a time. Each page lists its purpose, the fields and
measures to use, a suggested visual, and one point to make in an interview.

Two projects, two audiences:

| Project | Reads | Use it for |
|---|---|---|
| `powerbi\esg_lens_local\esg_lens_local.pbip` | `exports\local` (raw filed values included) | your own analysis; never shared, never screenshotted |
| `powerbi\esg_lens_public\esg_lens_public.pbip` | `exports\public` (the `rpt_public_*` models only) | anything that will be seen by others: screenshots and the demo video |

Build each page in the **public** project when it can be built there, and in the local one
when it needs local data (marked below). Only the public project may appear in a screenshot
or video ([publication_policy.md](publication_policy.md)).

## Before you start (once)

1. Run `.\scripts\dev.ps1 dbt-build` and then `.\scripts\dev.ps1 bi-export`. This writes the
   Parquet files to `exports\local` and `exports\public`.
2. Open the `.pbip` file in Power BI Desktop (version 2.158 or later; the projects are in the
   PBIP format with a TMDL model).
3. **Set the folder.** Home > Transform data > Edit parameters > `ExportFolder` = the full path
   of `exports\local` (local project) or `exports\public` (public project), without a
   backslash at the end, for example `D:\work\esg-lens-india\exports\public`. Close & Apply,
   then Refresh.
4. **Do not commit your path.** Saving writes it into `expressions.tmdl`. Before a commit run
   `git checkout -- powerbi/*/*.SemanticModel/definition/expressions.tmdl`, or once:
   `git update-index --skip-worktree` on those two files. A test fails if a drive path such as
   `D:\` is in `powerbi/`.
5. Check the six numbers in [powerbi_reconciliation.md](powerbi_reconciliation.md) before you
   build anything on top.

If a project does not open: create a blank report, open **TMDL view**, paste the whole of
`powerbi\esg_lens_local.tmdl-script.tmdl` (or the public one) and press Apply, then do step 3.
Single measures are also in `powerbi\esg_lens_local_measures.dax` and
`powerbi\esg_lens_public_measures.dax`.

### How the model is laid out

- Star schema: `dim_company` (one row per company, key `isin`) and `dim_fiscal_year` (sorted by
  financial year) filter the fact tables; every relationship runs one way, from dimension to
  fact.
- **Always slice by the dimensions** (`dim_company[sector_group]`,
  `dim_fiscal_year[fiscal_year_label]`), not by the copies of those columns in the fact tables.
- All measures are in the table **`_Measures`**, in display folders: 1 Coverage, 2 Intensity
  and shares, 3 Disclosure quality, 4 Restatements, 5 Data status and labels, 6 Concentration
  (local only), 7 Company card. Hover over a measure to read its description.
- Implicit measures are switched off: you cannot drag a column into a value well and get a sum.
  That is deliberate - the sum or average of an intensity column is never a right answer.
- **Whole group** (`... (whole group)`) = all emissions over all turnover of the companies in
  the selection; **typical company** (`... (typical company)`) = the median. Never average an
  intensity.
- In the public model the group figures come from `rpt_public_group_metrics`, one row per group
  type, group and year. A group figure shows a value only when exactly one such row is
  selected; it is blank when the group has fewer than 5 companies. Show `[Withheld note]` next
  to it so a blank is explained.

## Page 1 - Overview

**Purpose.** One screen that says what is covered and how the whole set looks in one year.

**Fields and measures.**

- Slicers: `dim_fiscal_year[fiscal_year_label]` (single select), and in the public model
  `rpt_public_group_metrics[group_type]` set to `all`.
- Cards (public): `[Companies in selection]`, `[GHG intensity, whole group]`,
  `[Disclosure Quality Score, typical company]`, `[Companies disclosing Scope 3 (%)]`,
  `[Renewable share of energy, whole group (%)]`, `[Figures materially restated (%)]` with
  `[Withheld note]` under it.
- Local equivalents: `[Companies in selection]`, `[GHG intensity (whole group)]`,
  `[DQS median]`, `[Scope 3 disclosed (% of reports)]`, `[Renewable share (whole group, %)]`,
  `[Material restatement share (%)]`.
- A text box or card with `[Year status]` (local) or `[Company: data status]` (public) for the
  provisional label.

**Visual.** A row of 5-6 KPI cards across the top, slicers on the left, a short text box
"What this is / what it is not" (not an ESG rating, not investment advice).

**Interview talking point.** "The cards look simple, but each one has a rule behind it: a
group figure is a ratio of sums or a median, never an average of ratios, and it is blank when
fewer than five companies stand behind it. The blank is a feature, and the card says why."

## Page 2 - Decarbonisation: whole group vs typical company

**Purpose.** Show that "is heavy industry decarbonising?" has two honest answers, and that the
answer changes when you follow the same companies (balanced panel).

**Fields and measures.**

- X axis: `dim_fiscal_year[fiscal_year_label]`; legend or small multiples:
  `dim_company[sector_group]`.
- Values: `[GHG intensity (whole group)]` and `[GHG intensity (typical company)]`.
- **Balanced-panel toggle (local):** a slicer on `dim_company[in_ghg_balanced_panel]` (true =
  the 38 companies that filed in every year with no comparability break). With it on, the
  Asset-heavy whole-group line goes up slightly (+3.7% over three years) while the typical
  company falls by about 38% - the finding of Q1.
- Alternative without DAX: the table `q01_ghg_intensity_by_sector` (Week 10 result) with
  `panel` as a slicer (`all companies` / `balanced panel`).
- Tooltip: `[Companies with GHG intensity]`, `[Public rule label]`.
- Public model: the same two lines from `[GHG intensity, whole group]` and
  `[GHG intensity, typical company]` with `rpt_public_group_metrics[group_type]` =
  `sector_group` and `rpt_public_group_metrics[group_value]` on the legend. The balanced panel is local only (the
  public table has no panel figure); quote the Week 10 percentages in a text box instead.

**Visual.** Two line charts side by side (whole group | typical company), one line per sector
group, the balanced-panel slicer above both. Use a log scale or small multiples: Asset-heavy is
about 50 times Asset-light.

**Interview talking point.** "The headline said heavy-industry intensity fell 15%. Follow the
same 15 companies and the whole group got slightly worse, while the typical company improved
38%. Composition and weighting decide the story, so the dashboard shows both and lets you
switch the panel."

## Page 3 - Concentration (Pareto)

**Purpose.** Show that a handful of companies carry most of the emissions. **Local only**: it
needs the emission totals, which are filed values.

**Fields and measures.**

- Axis: `dim_company[display_name]`, sorted by `[Scope 1+2 emissions (local only)]`
  descending; one year selected.
- Columns: `[Share of selected emissions (%)]`. Line: `[Cumulative share of emissions (%)]`.
  Optional: `[Emitter rank]` in the tooltip.
- Ready-made alternative: `q02_pareto_top10_by_year` (share and cumulative share of the ten
  largest emitters) and `q02_concentration_by_year` (top 1, 5, 10 shares).

**Visual.** Line and clustered column chart (Pareto), a constant line at 80%. Show shares on
the axis, never tonnes.

**For anything public**: do not screenshot this page. Quote the derived shares from
[analysis_findings.md](analysis_findings.md) (Q2: five companies hold about 85%) in a text box
of the public project - shares only, never tonnes.

**Interview talking point.** "Five companies are 85% of the emissions and ten are 98%. Any
average trend of this index is the trend of a power producer, two steel makers, a cement maker
and a refiner - which is why the other pages work with intensities and medians."

## Page 4 - Disclosure quality and data trust

**Purpose.** How good and how trustworthy is the reporting: scores, restatements, and which
figures are confirmed or still provisional.

**Fields and measures.**

- Slicer: one year (scores are comparable within a year only). Matrix rows:
  `dim_company[sector_group]` (local) or group type `sector_group` (public).
- Local: `[DQS median]`, `[DQS average]`, `[Grade A share (%)]`, `[Voluntary depth average]`,
  `[Companies with DQS]`; restatements `[Material restatement share (%)]`,
  `[Material restatements]`, `[Suspected scale errors]`.
- Public: `[Disclosure Quality Score, typical company]`, `[Company-years graded A (%)]`,
  `[Voluntary depth, average]`, `[Figures materially restated (%)]`, `[Withheld note]`.
- **Confirmed / provisional labels (local):** table `q03_yoy_changes_with_confidence` with
  `display_name`, `from_year`, `to_year`, `change_pct` and `[Confidence of YoY change]`;
  conditional formatting on `confidence` (confirmed = solid, everything else = grey and
  italic). Only `is_ranked = true` rows may be called leaders or laggards.
- Year label: `[Year status]` (local), `[Company: data status]` (public) in the page title.

**Visual.** Matrix with data bars for the scores; a 100% stacked bar of restatement classes by
year; a table for the year-on-year moves with the confidence label as its own coloured column.

**Interview talking point.** "Every year-on-year move larger than a factor of two turned out to
be a data problem, not performance. So this page labels each change as confirmed, provisional,
inferred unit, restated later or a one-year reversal, and only confirmed changes are ranked.
A league table without that label would rank the worst data, not the worst performers."

## Page 5 - Company card

**Purpose.** One company on one screen, placed among its peers without exposing filed values.

**Fields and measures.**

- Slicers: `dim_company[display_name]` (single select) and one year.
- Public cards: `[Company: GHG intensity]`, `[Peer median: GHG intensity]`, `[Company: DQS]`,
  `[Company: DQS grade]`, `[Company: DQS rank in group]`, `[Company: DQS percentile in group]`,
  `[Peer median: DQS]`, `[Company: renewable share (%)]`, `[Company: women in workforce (%)]`,
  `[Company: pay-equity gap (pp)]`, `[Company: data status]`.
- Local peer table: rows `fct_company_kpi_percentile[kpi_name]`, values `[Peer percentile]`,
  `[Peer median (ranking group)]`, `[Not ranked because]` (and `[Company value (local only)]`
  for yourself). The public project has percentiles only for the DQS: KPI percentiles are not
  in a public model yet, so do not rebuild them from company rows there.

**Visual.** Cards in a grid at the top; a bar or bullet chart of the percentiles (0-100, 100 =
best) with a reference line at 50; the reason codes of the score
(`rpt_public_disclosure_quality[dqs_reason_codes]`) in a small table.

**Interview talking point.** "The card never shows a filed tonne or rupee figure: only our
intensities, percentiles and scores, each with the peer median it should be read against, and
a provisional label when the next report has not confirmed the year yet."

## Colour, accessibility and labels

- **Colour.** Use one colour per sector group and keep it on every page (for example Asset-heavy
  dark blue, Asset-light teal, Financials orange). Use a colour-blind-safe palette (avoid red
  against green as the only difference) and never encode meaning by colour alone: add the label
  or an icon as well. Keep contrast at least 4.5:1 for text.
- **Withheld and provisional.** Withheld = grey with the text "n<5" (`[Withheld note]`), never
  a zero. Provisional = the same colour as final but lighter or hatched, with "Provisional"
  in the title or the data label (`[Year status]` or `[Company: data status]`). A note on
  every page: "FY2025-26 is provisional: no later report has confirmed it yet."
- **Accessibility.** Give every visual a title and alt text (Format > General > Alt text) that
  says what it shows; set the tab order (View > Selection); use font size 12 or more for text
  and avoid text inside images.
- **Units** in every title: "tCO2e per Rs crore", "%", "points (0-100)".
- **Disclaimer** on every page: "The Disclosure Quality Score is not an ESG rating, and this is
  not investment advice."

## Publishing

Dashboards are published **only as screenshots or a video of the public project**. The `.pbip`
files and `exports\local` are never shared. Before a screenshot: no filed absolute value on the
page (tonnes, GJ, kl, rupees, headcounts), no filed percentage, no link to the exchange, and
the provisional label visible where the latest year is shown.
