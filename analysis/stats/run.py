"""Run the Week 11 statistics studies and save every test as one row.

    python -m analysis.stats.run                 # all five studies
    python -m analysis.stats.run --only s3       # one study (no BH adjustment across studies)
    python -m analysis.stats.run --allow-empty   # a study without enough data is not an error
    python -m analysis.stats.run --no-mde        # skip the power simulations (fast)

Reads the gold tables (read-only) and writes data/processed/stats/stats_results.csv and
.json. That folder is local and never committed. What each study tests, and how, was fixed
beforehand in docs/stats_hypotheses.md; the findings are in docs/stats_findings.md.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

import duckdb
import pandas as pd

from analysis.stats import (
    common,
    s1_dqs_ghg,
    s2_decarbonisation,
    s3_restatements,
    s4_assurance,
    s5_ownership,
)
from analysis.stats.common import Outcome

ROOT = Path(__file__).resolve().parent.parent.parent
OUT_DIR = ROOT / "data" / "processed" / "stats"
DEFAULT_DB = ROOT / "data" / "warehouse" / "esg_lens.duckdb"
STUDIES = {
    "s1": s1_dqs_ghg,
    "s2": s2_decarbonisation,
    "s3": s3_restatements,
    "s4": s4_assurance,
    "s5": s5_ownership,
}


def run_studies(
    con: duckdb.DuckDBPyConnection, only: str | None = None, *, with_mde: bool = True
) -> list[Outcome]:
    """Run the studies and adjust the primary p-values (Benjamini-Hochberg over all of them)."""
    outcomes: list[Outcome] = []
    for name, module in STUDIES.items():
        if only and name != only:
            continue
        outcomes += module.run(con, with_mde=with_mde)
    common.adjust_primary(outcomes)
    return outcomes


def studies_without_result(outcomes: list[Outcome]) -> list[str]:
    """Studies in which no primary test could be run."""
    done = {o.study for o in outcomes if o.role == common.PRIMARY and o.status == common.OK}
    return sorted({o.study for o in outcomes} - done)


def _number(value: float | None, digits: int = 3) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "-"
    if math.isinf(value):
        return "inf" if value > 0 else "-inf"
    return f"{value:.{digits}f}"


def print_table(outcomes: list[Outcome]) -> None:
    header = f"{'test':<36} {'role':<11} {'n':>4} {'effect':>9} {'95% CI':>19} "
    print(header + f"{'p raw':>7} {'p BH':>7} {'MDE':>8}  decision")
    for o in outcomes:
        if o.status != common.OK:
            print(f"{o.test_id:<36} {o.role:<11} {o.n or 0:>4}  not enough data: {o.note}")
            continue
        interval = f"[{_number(o.ci_low)}, {_number(o.ci_high)}]" if o.ci_low is not None else "-"
        decision = {True: "reject H0", False: "do not reject H0", None: ""}[o.rejects_h0]
        if o.likely_underpowered:
            decision += " (likely underpowered)"
        print(
            f"{o.test_id:<36} {o.role:<11} {o.n:>4} {_number(o.effect):>9} {interval:>19} "
            f"{_number(o.p_raw, 4):>7} {_number(o.p_bh, 4):>7} {_number(o.mde):>8}  {decision}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=Path(os.getenv("DUCKDB_PATH") or DEFAULT_DB))
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    parser.add_argument("--only", choices=sorted(STUDIES), help="run one study only")
    parser.add_argument("--allow-empty", action="store_true")
    parser.add_argument("--no-mde", action="store_true", help="skip the power simulations")
    args = parser.parse_args(argv)

    if not args.db.exists():
        raise SystemExit(f"warehouse not found: {args.db} (run .\\scripts\\dev.ps1 dbt-build)")
    con = duckdb.connect(str(args.db), read_only=True)
    try:
        outcomes = run_studies(con, args.only, with_mde=not args.no_mde)
    finally:
        con.close()

    rows = [
        o.as_row() | {"rejects_h0": o.rejects_h0, "likely_underpowered": o.likely_underpowered}
        for o in outcomes
    ]
    args.out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(args.out / "stats_results.csv", index=False)
    (args.out / "stats_results.json").write_text(
        json.dumps(rows, indent=2, default=str), encoding="utf-8"
    )
    print_table(outcomes)
    print(f"{len(outcomes)} rows written to {args.out}")
    missing = studies_without_result(outcomes)
    if missing and not args.allow_empty:
        print("no primary test could be run in: " + ", ".join(missing))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
