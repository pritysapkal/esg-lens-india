"""Public safety checks on an exports/public folder (last task of the pipeline, also in pytest).

    python scripts/check_public.py exports/public

Fails when:
  1. a file other than the rpt_public_* Parquet files and the public workbook is in the folder;
  2. a Parquet column is named like a raw filed quantity (tonnes, GJ, kl, turnover, headcount,
     the hidden sums of the semantic layer, restatement values);
  3. rpt_public_group_metrics shows a statistic for fewer than 5 companies;
  4. rpt_public_company_percentile shows a value for a KPI that is not public_safe.
The same rules run inside dbt (assert_public_models_safe); this checks the files that leave.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from export_bi import PUBLIC_FILES  # noqa: E402

CATALOGUE = ROOT / "dbt" / "seeds" / "kpi_catalogue.csv"
RAW_NAME = re.compile(
    r"(_tco2e|_gj|_kl|_t)(_annualised)?$|turnover|headcount|_num$|_den$|^original_value$"
    r"|^restated_value$|^abs_change$|^stated_reason$|^value$"
)
STATISTICS = {"ratio_of_sums", "median", "average", "share"}


def _catalogue() -> list[dict[str, str]]:
    with CATALOGUE.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def problems(folder: Path) -> list[str]:
    found: list[str] = []
    files = {p.name for p in folder.iterdir() if p.is_file() and p.name != ".gitkeep"}
    found += [f"not allowed in the public folder: {name}" for name in sorted(files - PUBLIC_FILES)]
    tables = {p.stem: pd.read_parquet(p) for p in sorted(folder.glob("rpt_public_*.parquet"))}
    for name, frame in tables.items():
        found += [f"raw-value column {name}.{c}" for c in frame.columns if RAW_NAME.search(c)]

    catalogue = _catalogue()
    groups = tables.get("rpt_public_group_metrics")
    if groups is not None:
        for row in catalogue:
            if row["metric_type"] in STATISTICS and row["kpi_name"] in groups:
                gate = groups[row["companies_metric"]].fillna(0)
                shown = groups[row["kpi_name"]].notna() & (gate < 5)
                found += [
                    f"{row['kpi_name']} shown for fewer than 5 companies: "
                    f"{r.group_type} / {r.group_value} / {r.fiscal_year_label}"
                    for r in groups[shown].itertuples()
                ]
    percentiles = tables.get("rpt_public_company_percentile")
    if percentiles is not None:
        public = {
            r["kpi_name"]
            for r in catalogue
            if r["metric_type"] == "company_value" and r["public_safe"] == "true"
        }
        filed = percentiles[
            percentiles["kpi_value_public"].notna() & ~percentiles["kpi_name"].isin(public)
        ]
        found += [f"filed value shown for {k}" for k in sorted(set(filed["kpi_name"]))]
    return found


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    folder = Path(args[0]) if args else ROOT / "exports" / "public"
    if not folder.is_dir():
        print(f"no folder {folder}", file=sys.stderr)
        return 1
    found = problems(folder)
    for problem in found:
        print(problem, file=sys.stderr)
    if found:
        return 1
    print(f"public safety checks passed: {folder}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
