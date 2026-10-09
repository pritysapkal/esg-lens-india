"""Cross-check ingestion.parse_xbrl against Arelle (offline) on five reference filings.

Run after ``python -m ingestion.parse_xbrl``:   python scripts/arelle_crosscheck.py

The filings' schemaRef is a bare file name (``in-capmkt-ent-<version>.xsd``), so Arelle only
finds the taxonomy when the instance sits next to it. Each filing is therefore copied, together
with its local taxonomy version (``BRSR/`` + ``core/`` from data/raw/taxonomy), into a temporary
directory that is deleted afterwards. Arelle runs with ``workOffline`` and validation off; the
core XBRL schemas come from Arelle's bundled cache. Nothing is fetched from the network.

Compared per filing: fact / context / unit counts, 20 randomly sampled numeric facts (same
concept + context + unit, raw string and decimal value), every fact (concept, context, unit, nil,
value), and every context (period + dimensions).

Outputs:
- the results table in ``docs/parser_validation.md`` (between the ``results`` markers) -
  counts and match rates only, no filed values;
- ``data/processed/arelle_crosscheck_values.csv`` (git-ignored) with the sampled values.
"""

from __future__ import annotations

import random
import shutil
import sys
import tempfile
from collections import Counter
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingestion import config  # noqa: E402

TARGETS = [  # (symbol, reporting_year_label, short label)
    ("HDFCBANK", "2025-2026", "FY26"),
    ("RELIANCE", "2024-2025", "FY25"),
    ("TCS", "2023-2024", "FY24"),
    ("SBIN", "2022-2023", "FY23"),
    ("NESTLEIND", "2023-2024", "2023-2024"),
]
N_SAMPLE = 20
SEED = 20261009
DOC = config.DOCS_DIR / "parser_validation.md"
VALUES_CSV = config.PROCESSED_DIR / "arelle_crosscheck_values.csv"
START, END = "<!-- results:start -->", "<!-- results:end -->"


def _read(table: str, filing_id: str) -> pd.DataFrame:
    files = list((config.PARSED_DIR / table).glob(f"*/{filing_id}.parquet"))
    if not files:
        raise SystemExit(f"{table} for {filing_id} not parsed - run python -m ingestion.parse_xbrl")
    return pd.read_parquet(files[0])


def _taxonomy_root(version: str) -> Path:
    """Folder holding ``BRSR/`` and ``core/`` for ``version`` (layouts differ per package)."""
    versions = pd.read_csv(config.TAXONOMY_VERSIONS_CSV, dtype=str, keep_default_na=False)
    entry = versions.loc[versions["version"] == version, "path_to_entry_xsd"]
    if entry.empty or not entry.iloc[0]:
        raise FileNotFoundError(f"taxonomy {version} not on disk")
    return (config.REPO_ROOT / entry.iloc[0]).parent.parent


def _decimal(value) -> Decimal | None:
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, TypeError):
        return None


def _arelle_dimension_key(ctx) -> str:
    parts = []
    for dim in ctx.qnameDims.values():
        if dim.isExplicit:
            member = dim.memberQname.localName
        else:
            member = "".join(dim.typedMember.itertext()).strip()
        parts.append((dim.dimensionQname.localName, member))
    return "|".join(f"{axis}={member}" for axis, member in sorted(parts))


def _arelle_period(ctx) -> tuple:
    # Arelle stores end / instant dates as the following midnight; subtract one day back.
    if ctx.isInstantPeriod:
        return ("instant", None, None, ctx.instantDatetime.date() - timedelta(days=1))
    if ctx.isStartEndPeriod:
        end = ctx.endDatetime.date() - timedelta(days=1)
        return ("duration", ctx.startDatetime.date(), end, None)
    return ("forever", None, None, None)


def load_with_arelle(xml_path: Path, taxonomy_root: Path, workdir: Path):
    """Stage instance + taxonomy in ``workdir`` and load offline. Returns (controller, model)."""
    from arelle import Cntlr, ModelXbrl

    for sub in ("BRSR", "core"):
        shutil.copytree(taxonomy_root / sub, workdir / sub)
    staged = workdir / "BRSR" / xml_path.name
    shutil.copy2(xml_path, staged)
    cntlr = Cntlr.Cntlr(logFileName="logToBuffer")
    cntlr.webCache.workOffline = True
    cntlr.modelManager.validateDisclosureSystem = False
    model = ModelXbrl.load(cntlr.modelManager, str(staged))
    return cntlr, model


def check_filing(filing: dict, rng: random.Random) -> tuple[dict, list[dict]]:
    fid = filing["filing_id"]
    ours = pd.concat([_read("facts", fid), _read("text_facts", fid)], ignore_index=True)
    ours = ours.astype(object).where(ours.notna(), None)  # pandas reads NULL strings as NaN
    contexts = _read("contexts", fid)
    units = _read("units", fid)

    with tempfile.TemporaryDirectory(prefix="arelle_xcheck_") as tmp:
        root = _taxonomy_root(filing["taxonomy_version"])
        cntlr, model = load_with_arelle(config.REPO_ROOT / filing["path"], root, Path(tmp))
        try:
            records = cntlr.logHandler.logRecordBuffer
            errors = [f"{r.levelname}: {r.getMessage()}" for r in records if r.levelno >= 30]
            a_facts = list(model.facts)
            n_a_contexts, n_a_units = len(model.contexts), len(model.units)
            undefined = sum(f.concept is None for f in a_facts)

            def key(ns, name, ctx, unit):
                return (ns, name, ctx, unit or None)

            a_index: dict[tuple, list] = {}
            a_full = Counter()
            for f in a_facts:
                k = key(f.qname.namespaceURI, f.qname.localName, f.contextID, f.unitID)
                a_index.setdefault(k, []).append(f)
                a_full[(*k, f.isNil, None if f.isNil else f.value)] += 1
            o_full = Counter(
                (*key(r.namespace, r.concept, r.context_ref, r.unit_ref), r.is_nil, r.raw_value)
                for r in ours.itertuples()
            )
            # Context-by-context: period + dimension_key
            a_ctx = {
                cid: (*_arelle_period(c), _arelle_dimension_key(c))
                for cid, c in model.contexts.items()
            }
            o_ctx = {
                r.context_id: (
                    r.period_type,
                    r.start_date if pd.notna(r.start_date) else None,
                    r.end_date if pd.notna(r.end_date) else None,
                    r.instant_date if pd.notna(r.instant_date) else None,
                    r.dimension_key,
                )
                for r in contexts.itertuples()
            }
            ctx_match = sum(o_ctx.get(cid) == v for cid, v in a_ctx.items())

            numeric = ours[ours["is_numeric"] & ~ours["is_nil"]].sort_values("sequence")
            sample = numeric.iloc[sorted(rng.sample(range(len(numeric)), N_SAMPLE))]
            values = []
            for r in sample.itertuples():
                matches = a_index.get(key(r.namespace, r.concept, r.context_ref, r.unit_ref), [])
                a_val = matches[0].value if len(matches) == 1 else None
                values.append(
                    {
                        "symbol": filing["symbol"],
                        "reporting_year_label": filing["reporting_year_label"],
                        "concept": r.concept,
                        "context_ref": r.context_ref,
                        "unit_ref": r.unit_ref,
                        "parser_raw_value": r.raw_value,
                        "arelle_value": a_val,
                        "n_arelle_matches": len(matches),
                        "string_equal": a_val == r.raw_value,
                        "decimal_equal": a_val is not None
                        and _decimal(a_val) == _decimal(r.raw_value),
                    }
                )
        finally:
            model.close()
            cntlr.close()

    result = {
        "filing": f"{filing['symbol']} {filing['label']}",
        "taxonomy": filing["taxonomy_version"],
        "facts": (len(ours), len(a_facts)),
        "contexts": (len(contexts), n_a_contexts),
        "units": (len(units), n_a_units),
        "undefined": undefined,
        "sample_equal": sum(v["string_equal"] and v["decimal_equal"] for v in values),
        "all_facts_equal": sum((o_full & a_full).values()),
        "contexts_equal": ctx_match,
        "errors": errors,
    }
    return result, values


def _pair(p: tuple[int, int]) -> str:
    ours, theirs = p
    return f"{ours:,} / {theirs:,} {'✅' if ours == theirs else '❌'}"


def results_table(results: list[dict]) -> str:
    lines = [
        "| Filing | Taxonomy | Facts (parser / Arelle) | Contexts | Units | "
        f"{N_SAMPLE} sampled numeric values equal | All facts equal | All contexts equal |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['filing']} | {r['taxonomy']} | {_pair(r['facts'])} | {_pair(r['contexts'])} | "
            f"{_pair(r['units'])} | {r['sample_equal']}/{N_SAMPLE} | "
            f"{r['all_facts_equal']:,}/{r['facts'][1]:,} | "
            f"{r['contexts_equal']:,}/{r['contexts'][1]:,} |"
        )
    return "\n".join(lines)


def main() -> None:
    manifest = pd.read_csv(config.MANIFEST_PATH, dtype=str, keep_default_na=False)
    rng = random.Random(SEED)
    results, all_values = [], []
    for symbol, year, label in TARGETS:
        rows = manifest[(manifest["symbol"] == symbol) & (manifest["reporting_year_label"] == year)]
        if rows.empty:
            print(f"{symbol} {year}: not in manifest - skipped")
            continue
        filing = {**rows.iloc[0].to_dict(), "label": label}
        result, values = check_filing(filing, rng)
        results.append(result)
        all_values.extend(values)
        print(
            f"{result['filing']:<20} facts {_pair(result['facts'])}  contexts "
            f"{_pair(result['contexts'])}  units {_pair(result['units'])}  sample "
            f"{result['sample_equal']}/{N_SAMPLE}  all facts {result['all_facts_equal']:,}  "
            f"contexts equal {result['contexts_equal']:,}  undefined concepts "
            f"{result['undefined']}  arelle errors {len(result['errors'])}"
        )
        for err in result["errors"][:5]:
            print(f"    {err}")

    pd.DataFrame(all_values).to_csv(VALUES_CSV, index=False, lineterminator="\n")
    table = results_table(results)
    doc = DOC.read_text(encoding="utf-8")
    head, rest = doc.split(START, 1)
    _, tail = rest.split(END, 1)
    DOC.write_text(f"{head}{START}\n{table}\n{END}{tail}", encoding="utf-8", newline="\n")
    print(f"-> {config.display_path(DOC)}, {config.display_path(VALUES_CSV)}")


if __name__ == "__main__":
    main()
