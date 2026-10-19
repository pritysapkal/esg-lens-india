"""Export the warehouse for Power BI and Excel (Week 12) as Parquet files.

    python scripts/export_bi.py                  # both folders, and the public Excel workbook
    python scripts/export_bi.py --only public    # exports/public only
    python scripts/export_bi.py --no-excel       # skip the workbooks

Two folders, two audiences (docs/publication_policy.md):

  exports/local/   the star schema with every column, including the filed values behind the
                   ratio-of-sums measures, and the Week 10 result tables. Gitignored, never
                   shared: it holds raw filed values.
  exports/public/  ONLY the seven rpt_public_* models, plus the Excel workbook built from them.
                   Nothing else may land here; the script refuses to finish if it does.
                   Fractional values are rounded to PUBLIC_DECIMALS (6) decimals, so the
                   committed files change only when the data does.

Power BI reads these files through the ExportFolder parameter (powerbi/, see
docs/powerbi_build_guide.md). Rebuild with `.\\scripts\\dev.ps1 bi-export` after every dbt build.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analysis.stats.data import PANEL_SQL  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "warehouse" / "esg_lens.duckdb"
EXPORTS = ROOT / "exports"
PUBLIC_WORKBOOK = "esg_lens_public.xlsx"
LOCAL_WORKBOOK = "esg_lens_local.xlsx"

# The star schema for the local model. One query per file; the Power BI model is generated from
# the same queries (scripts/build_powerbi.py), so a column added here reaches the model too.
LOCAL_TABLES: dict[str, str] = {
    # dim_company plus the balanced-panel flag of Week 10 (Q1 / Q5): filed in every year with a
    # GHG intensity and no comparability break after the first year. Drives the panel toggle.
    "dim_company": f"""
        select
            company.*,
            panel.isin is not null as in_ghg_balanced_panel
        from dim_company as company
        left join ({PANEL_SQL}) as panel on company.isin = panel.isin
        order by company.isin
    """,
    # only the years that have filings (the seed also lists two comparative-only years)
    "dim_fiscal_year": """
        select *
        from dim_fiscal_year
        where fiscal_year_label in (select fiscal_year_label from fct_company_year)
        order by fy_sort
    """,
    "dim_metric": "select * from dim_metric order by sort_order, metric_id",
    "fct_company_year": "select * from fct_company_year order by isin, fiscal_year_label",
    "fct_disclosure_quality": (
        "select * from fct_disclosure_quality order by isin, fiscal_year_label"
    ),
    "fct_restatement": (
        "select * from fct_restatement "
        "order by isin, value_fiscal_year_label, metric_id, dimension_key"
    ),
    "fct_company_kpi_percentile": (
        "select * from fct_company_kpi_percentile order by isin, fiscal_year_label, kpi_name"
    ),
    "fct_peer_benchmark": (
        "select * from fct_peer_benchmark order by ranking_group, fiscal_year_label, kpi_name"
    ),
}

# The public folder: the rpt_public_* models and nothing else.
PUBLIC_TABLES: dict[str, str] = {
    # sorted, so the committed public files change only when the data does
    name: f"select * from {name} order by all"
    for name in (
        "rpt_public_company_year",
        "rpt_public_disclosure_quality",
        "rpt_public_group_metrics",
        "rpt_public_restatement_summary",
        "rpt_public_concentration",
        "rpt_public_company_percentile",
        "rpt_public_ghg_yoy",
    )
}
PUBLIC_FILES = {f"{name}.parquet" for name in PUBLIC_TABLES} | {PUBLIC_WORKBOOK}
# Fractional columns of the public files are rounded to this many decimals, so that a rebuild on
# the same data writes the same bytes: floating-point noise in the last digits (summation order,
# DuckDB threads) would otherwise change the committed Parquet files without any real change.
PUBLIC_DECIMALS = 6

# Week 10 results that the local Power BI model loads (all of them are exported).
ANALYSIS_IN_MODEL = [
    "q01_decarbonisation__ghg_intensity_by_sector",
    "q02_emission_concentration__concentration_by_year",
    "q02_emission_concentration__pareto_top10_by_year",
    "q03_ghg_leaders_laggards__yoy_changes_with_confidence",
]


def _load_runner():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_analysis", ROOT / "scripts" / "run_analysis.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_analysis"] = module
    spec.loader.exec_module(module)
    return module


def analysis_queries() -> dict[str, str]:
    """The Week 10 queries, keyed by result id."""
    return {query.result_id: query.sql for query in _load_runner().load_queries()}


def describe(con: duckdb.DuckDBPyConnection, sql: str) -> list[tuple[str, str]]:
    """(column, DuckDB type) of a query's result, as it will be written to Parquet."""
    relation = con.sql(sql)
    return [(name, str(kind)) for name, kind in zip(relation.columns, relation.types, strict=True)]


def portable(con: duckdb.DuckDBPyConnection, sql: str, decimals: int | None = None) -> str:
    """The query with DECIMAL and HUGEINT columns cast to DOUBLE and BIGINT, so that Power BI
    and Excel see plain numbers (Parquet decimals load as fixed decimals in Power BI). With
    `decimals`, every fractional column (DOUBLE, FLOAT, DECIMAL) is also rounded to that many
    decimals; whole-number columns are exact already."""
    columns = describe(con, sql)
    fractional = ("DECIMAL", "DOUBLE", "FLOAT", "REAL")
    if not any(
        kind.startswith(("DECIMAL", "HUGEINT"))
        or (decimals is not None and kind.startswith(fractional))
        for _, kind in columns
    ):
        return sql
    parts = []
    for name, kind in columns:
        quoted = '"' + name.replace('"', '""') + '"'
        if decimals is not None and kind.startswith(fractional):
            parts.append(f"round(cast({quoted} as double), {decimals}) as {quoted}")
        elif kind.startswith("DECIMAL"):
            parts.append(f"cast({quoted} as double) as {quoted}")
        elif kind.startswith("HUGEINT"):
            parts.append(f"cast({quoted} as bigint) as {quoted}")
        else:
            parts.append(quoted)
    return f"select {', '.join(parts)} from ({sql}) as exported"


def _write(
    con: duckdb.DuckDBPyConnection, sql: str, path: Path, decimals: int | None = None
) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    query = portable(con, sql, decimals)
    if decimals is not None:
        # sort again after rounding: rows that differed only by noise keep a fixed order
        query = f"select * from ({query}) as rounded order by all"
    relation = con.sql(query)
    relation.write_parquet(str(path))
    return len(relation)


def _clear(folder: Path) -> None:
    """Remove earlier exports so that nothing stale stays behind (the .gitkeep stays)."""
    if not folder.exists():
        return
    for path in sorted(folder.rglob("*"), reverse=True):
        if path.is_file() and path.name != ".gitkeep":
            path.unlink()
        elif path.is_dir() and not any(path.iterdir()):
            path.rmdir()


def assert_public_only(folder: Path) -> None:
    """Fail if anything but the rpt_public_* files and the public workbook is in the folder."""
    found = {
        path.relative_to(folder).as_posix()
        for path in folder.rglob("*")
        if path.is_file() and path.name != ".gitkeep"
    }
    unexpected = sorted(found - PUBLIC_FILES)
    if unexpected:
        raise SystemExit(f"not allowed in {folder}: {unexpected} (publication policy)")


def export_local(con: duckdb.DuckDBPyConnection, folder: Path) -> dict[str, int]:
    _clear(folder)
    rows = {
        name: _write(con, sql, folder / f"{name}.parquet") for name, sql in LOCAL_TABLES.items()
    }
    for result_id, sql in analysis_queries().items():
        rows[f"analysis/{result_id}"] = _write(
            con, sql, folder / "analysis" / f"{result_id}.parquet"
        )
    return rows


def export_public(con: duckdb.DuckDBPyConnection, folder: Path) -> dict[str, int]:
    _clear(folder)
    rows = {
        name: _write(con, sql, folder / f"{name}.parquet", PUBLIC_DECIMALS)
        for name, sql in PUBLIC_TABLES.items()
    }
    assert_public_only(folder)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=Path(os.getenv("DUCKDB_PATH") or DEFAULT_DB))
    parser.add_argument("--out", type=Path, default=EXPORTS)
    parser.add_argument("--only", choices=["local", "public"])
    parser.add_argument("--no-excel", action="store_true", help="do not build the workbooks")
    args = parser.parse_args(argv)

    if not args.db.exists():
        raise SystemExit(f"warehouse not found: {args.db} (run .\\scripts\\dev.ps1 dbt-build)")
    con = duckdb.connect(str(args.db), read_only=True)
    try:
        written: dict[str, dict[str, int]] = {}
        if args.only in (None, "local"):
            written["local"] = export_local(con, args.out / "local")
        if args.only in (None, "public"):
            written["public"] = export_public(con, args.out / "public")
    finally:
        con.close()

    if not args.no_excel:
        import build_excel

        if "public" in written:
            build_excel.build(args.out / "public", args.out / "public" / PUBLIC_WORKBOOK)
            assert_public_only(args.out / "public")
        if "local" in written and "public" in written:
            build_excel.build(
                args.out / "public",
                args.out / "local" / LOCAL_WORKBOOK,
                local_folder=args.out / "local",
            )

    for audience, files in written.items():
        print(f"{audience}: {len(files)} tables")
        for name, n in files.items():
            print(f"  {name:<70} {n:>6} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
