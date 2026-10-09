"""Parse BRSR XBRL instance documents into Parquet tables (lxml iterparse, no network).

Input: the intake manifest (``data/raw/manifest.csv``), one row per received filing.
Output: five tables under ``data/processed/parsed/<table>/reporting_year_label=<label>/``,
one Parquet file per filing (``<filing_id>.parquet``):

- ``filings``    : one row per filing - counts, main reporting period, parse timing.
- ``contexts``   : entity identifier, period (duration / instant) and dimensions as JSON plus a
                   stable ``dimension_key`` ("AxisA=MemberX|AxisB=MemberY", sorted by axis).
- ``units``      : measures, incl. ``xbrli:divide`` numerator / denominator.
- ``facts``      : numeric and short non-numeric facts.
- ``text_facts`` : long text - concept ends with ``TextBlock`` or value longer than 1,000 chars.

Rules:
- ``raw_value`` is ALWAYS the string exactly as filed (after XML decoding); casting happens in
  dbt staging. Nil facts (``xsi:nil="true"``) have ``raw_value = NULL``.
- Each file has current-year AND prior-year values; both are kept (contexts distinguish them).
- Re-running is idempotent: a re-parsed filing replaces only its own files. A filing that fails
  to parse loses its stale output files and gets a row in ``data/processed/parse_errors.csv``;
  the run continues with the next filing.

CLI: ``python -m ingestion.parse_xbrl [--only SYMBOL] [--limit N]``
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from lxml import etree

from ingestion import config
from ingestion.instance import (
    LINK_NS,
    SCHEMA_REF_TAG,
    XBRLI_NS,
    XLINK_NS,
    XSI_NIL,
    InstanceError,
    taxonomy_version_from_href,
)
from ingestion.intake import read_manifest

PARSER_VERSION = "1.0.0"
TEXT_MIN_CHARS = 1000  # values longer than this go to text_facts
PARTITION_COL = "reporting_year_label"

XBRLDI_NS = "http://xbrl.org/2006/xbrldi"
XBRL_TAG = f"{{{XBRLI_NS}}}xbrl"
CONTEXT_TAG = f"{{{XBRLI_NS}}}context"
UNIT_TAG = f"{{{XBRLI_NS}}}unit"
EXPLICIT_MEMBER_TAG = f"{{{XBRLDI_NS}}}explicitMember"
TYPED_MEMBER_TAG = f"{{{XBRLDI_NS}}}typedMember"

SCHEMAS: dict[str, pa.Schema] = {
    "filings": pa.schema(
        [
            ("filing_id", pa.string()),
            ("symbol", pa.string()),
            ("isin", pa.string()),
            ("taxonomy_version", pa.string()),
            ("file_path", pa.string()),
            ("n_facts", pa.int32()),  # n_numeric + non-numeric short facts + n_text
            ("n_numeric", pa.int32()),  # facts with a unitRef
            ("n_text", pa.int32()),  # rows in text_facts
            ("n_nil", pa.int32()),
            ("n_concepts", pa.int32()),
            ("n_contexts", pa.int32()),
            ("n_units", pa.int32()),
            ("n_dimension_axes", pa.int32()),
            ("main_context_id", pa.string()),
            ("period_start", pa.date32()),
            ("period_end", pa.date32()),
            ("period_days", pa.int32()),  # inclusive of both ends
            ("period_months", pa.int32()),
            ("is_non_standard_period", pa.bool_()),
            ("parse_seconds", pa.float64()),
            ("parser_version", pa.string()),
        ]
    ),
    "contexts": pa.schema(
        [
            ("filing_id", pa.string()),
            ("context_id", pa.string()),
            ("identifier_scheme", pa.string()),
            ("identifier_value", pa.string()),
            ("period_type", pa.string()),  # duration | instant | forever
            ("start_date", pa.date32()),
            ("end_date", pa.date32()),
            ("instant_date", pa.date32()),
            ("dimensions", pa.string()),  # JSON list of {axis, member, member_type}
            ("dimension_key", pa.string()),
        ]
    ),
    "units": pa.schema(
        [
            ("filing_id", pa.string()),
            ("unit_id", pa.string()),
            ("numerator_measures", pa.list_(pa.string())),
            ("denominator_measures", pa.list_(pa.string())),
            ("unit_label", pa.string()),
        ]
    ),
}
SCHEMAS["facts"] = SCHEMAS["text_facts"] = pa.schema(
    [
        ("filing_id", pa.string()),
        ("concept", pa.string()),  # local name
        ("namespace", pa.string()),
        ("prefix", pa.string()),
        ("context_ref", pa.string()),
        ("unit_ref", pa.string()),
        ("decimals", pa.string()),
        ("raw_value", pa.string()),  # exactly as filed; NULL when nil
        ("is_nil", pa.bool_()),
        ("is_numeric", pa.bool_()),
        ("fact_id", pa.string()),
        ("sequence", pa.int32()),  # 1-based order among all facts in the file
    ]
)
TABLES: tuple[str, ...] = ("filings", "contexts", "units", "facts", "text_facts")
ERROR_COLUMNS = ["filing_id", "symbol", PARTITION_COL, "path", "error_type", "error", "logged_at"]


@dataclass
class ParsedInstance:
    """Rows of one instance; ``filings`` holds a single summary row."""

    schema_ref: str = ""
    contexts: list[dict] = field(default_factory=list)
    units: list[dict] = field(default_factory=list)
    facts: list[dict] = field(default_factory=list)
    text_facts: list[dict] = field(default_factory=list)
    filings: list[dict] = field(default_factory=list)

    def table(self, name: str) -> pa.Table:
        return pa.Table.from_pylist(getattr(self, name), schema=SCHEMAS[name])


@dataclass
class RunSummary:
    parsed: list[dict] = field(default_factory=list)  # filings rows
    failed: list[dict] = field(default_factory=list)  # error rows
    facts_by_taxonomy: Counter[str] = field(default_factory=Counter)
    totals: Counter[str] = field(default_factory=Counter)
    seconds: float = 0.0


# --- element parsing ---------------------------------------------------------------------------


def _local(qname: str) -> str:
    """``prefix:Local`` -> ``Local``."""
    return qname.rsplit(":", 1)[-1]


def _date(text: str | None) -> date | None:
    """xs:date or xs:dateTime -> date (date part only)."""
    return date.fromisoformat(text.strip()[:10]) if text and text.strip() else None


def _key_member(dim: dict) -> str:
    """Explicit members by local name; typed members by their value."""
    return _local(dim["member"]) if dim["member_type"] == "explicit" else dim["member"]


def parse_context(el: etree._Element, filing_id: str) -> dict:
    """One ``xbrli:context`` -> contexts row. Dimensions may sit in segment or scenario."""
    identifier = el.find(f"{{{XBRLI_NS}}}entity/{{{XBRLI_NS}}}identifier")
    period = el.find(f"{{{XBRLI_NS}}}period")
    if period is None:
        raise InstanceError(f"context {el.get('id')!r} has no period")
    instant = period.find(f"{{{XBRLI_NS}}}instant")
    if instant is not None:
        period_type = "instant"
    elif period.find(f"{{{XBRLI_NS}}}forever") is not None:
        period_type = "forever"
    else:
        period_type = "duration"

    dims = []
    for member in el.iter(EXPLICIT_MEMBER_TAG, TYPED_MEMBER_TAG):
        if member.tag == EXPLICIT_MEMBER_TAG:
            value, member_type = (member.text or "").strip(), "explicit"
        else:
            value = "".join(member.itertext()).strip()  # text of the typed domain element
            member_type = "typed"
        dims.append(
            {"axis": member.get("dimension", ""), "member": value, "member_type": member_type}
        )
    dims.sort(key=lambda d: (_local(d["axis"]), d["axis"]))
    dimension_key = "|".join(f"{_local(d['axis'])}={_key_member(d)}" for d in dims)

    return {
        "filing_id": filing_id,
        "context_id": el.get("id"),
        "identifier_scheme": identifier.get("scheme") if identifier is not None else None,
        "identifier_value": (identifier.text or "").strip() if identifier is not None else None,
        "period_type": period_type,
        "start_date": _date(period.findtext(f"{{{XBRLI_NS}}}startDate")),
        "end_date": _date(period.findtext(f"{{{XBRLI_NS}}}endDate")),
        "instant_date": _date(instant.text) if instant is not None else None,
        "dimensions": json.dumps(dims, ensure_ascii=False),
        "dimension_key": dimension_key,
    }


def _measures(parent: etree._Element | None) -> list[str]:
    if parent is None:
        return []
    return [(m.text or "").strip() for m in parent.findall(f"{{{XBRLI_NS}}}measure")]


def unit_label(numerator: list[str], denominator: list[str]) -> str:
    """Human label from measure local names, e.g. ``tCO2e/INR`` or ``INR``."""
    num = "*".join(_local(m) for m in numerator)
    return f"{num}/{'*'.join(_local(m) for m in denominator)}" if denominator else num


def parse_unit(el: etree._Element, filing_id: str) -> dict:
    """One ``xbrli:unit`` -> units row (simple measures or ``xbrli:divide``)."""
    divide = el.find(f"{{{XBRLI_NS}}}divide")
    if divide is not None:
        numerator = _measures(divide.find(f"{{{XBRLI_NS}}}unitNumerator"))
        denominator = _measures(divide.find(f"{{{XBRLI_NS}}}unitDenominator"))
    else:
        numerator, denominator = _measures(el), []
    return {
        "filing_id": filing_id,
        "unit_id": el.get("id"),
        "numerator_measures": numerator,
        "denominator_measures": denominator,
        "unit_label": unit_label(numerator, denominator),
    }


def fact_hash(filing_id: str, sequence: int, tag: str, context_ref, unit_ref) -> str:
    key = f"{filing_id}|{sequence}|{tag}|{context_ref or ''}|{unit_ref or ''}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def is_text_fact(concept: str, raw_value: str | None) -> bool:
    return concept.endswith("TextBlock") or len(raw_value or "") > TEXT_MIN_CHARS


def parse_fact(el: etree._Element, filing_id: str, sequence: int) -> dict:
    """One top-level fact element -> facts / text_facts row (``raw_value`` never cast)."""
    if len(el):
        raise InstanceError(f"tuple {el.tag} is not supported")
    qname = etree.QName(el)
    is_nil = el.get(XSI_NIL) in ("true", "1")
    unit_ref = el.get("unitRef")
    return {
        "filing_id": filing_id,
        "concept": qname.localname,
        "namespace": qname.namespace,
        "prefix": el.prefix,
        "context_ref": el.get("contextRef"),
        "unit_ref": unit_ref,
        "decimals": el.get("decimals"),
        "raw_value": None if is_nil else (el.text or ""),
        "is_nil": is_nil,
        "is_numeric": unit_ref is not None,
        "fact_id": el.get("id")
        or fact_hash(filing_id, sequence, el.tag, el.get("contextRef"), unit_ref),
        "sequence": sequence,
    }


def parse_instance(xml_path: Path, filing_id: str) -> ParsedInstance:
    """Stream one instance with ``iterparse``; each top-level element is freed once handled.

    Skips ``link:*`` (schemaRef, footnoteLink, roleRef, ...) when collecting facts. lxml reads the
    XML declaration / BOM, so UTF-8 (with or without BOM) and UTF-16 files parse the same.
    """
    out = ParsedInstance()
    depth = 0
    sequence = 0
    try:
        events = etree.iterparse(
            str(xml_path),
            events=("start", "end"),
            huge_tree=True,
            remove_comments=True,
            remove_pis=True,
        )
        for event, el in events:
            if event == "start":
                depth += 1
                if depth == 1 and el.tag != XBRL_TAG:
                    raise InstanceError(f"root element is {el.tag}, not xbrli:xbrl")
                continue
            depth -= 1
            if depth != 1:
                continue  # descendants are handled with their top-level element

            tag = el.tag
            if tag == CONTEXT_TAG:
                out.contexts.append(parse_context(el, filing_id))
            elif tag == UNIT_TAG:
                out.units.append(parse_unit(el, filing_id))
            elif tag == SCHEMA_REF_TAG:
                out.schema_ref = el.get(f"{{{XLINK_NS}}}href", "")
            elif isinstance(tag, str) and etree.QName(el).namespace not in (XBRLI_NS, LINK_NS):
                sequence += 1
                row = parse_fact(el, filing_id, sequence)
                target = (
                    out.text_facts if is_text_fact(row["concept"], row["raw_value"]) else out.facts
                )
                target.append(row)

            el.clear(keep_tail=True)
            parent = el.getparent()
            while el.getprevious() is not None:
                del parent[0]
    except etree.XMLSyntaxError as exc:
        raise InstanceError(f"not well-formed XML ({exc})") from exc
    if not out.schema_ref:
        raise InstanceError("no link:schemaRef found")
    return out


# --- filing summary ------------------------------------------------------------------------------


def main_period(contexts: list[dict], fact_rows: list[dict]) -> dict | None:
    """The current-year main duration context: no dimensions, latest end date.

    Ties (several dimensionless durations ending on the same day) go to the context with the
    most facts, then the earliest start.
    """
    refs = Counter(row["context_ref"] for row in fact_rows)
    candidates = [
        c
        for c in contexts
        if c["period_type"] == "duration" and not c["dimension_key"] and c["end_date"]
    ]
    if not candidates:
        return None
    latest = max(c["end_date"] for c in candidates)
    best = sorted(
        (c for c in candidates if c["end_date"] == latest),
        key=lambda c: (-refs[c["context_id"]], c["start_date"] or date.max, c["context_id"]),
    )[0]
    return best


def period_months(days: int) -> int:
    """Inclusive day count -> whole months (365 days -> 12, 456 days -> 15)."""
    return round(days / (365.25 / 12))


def summarise(parsed: ParsedInstance, filing: dict, seconds: float) -> dict:
    all_facts = parsed.facts + parsed.text_facts
    main = main_period(parsed.contexts, all_facts)
    start = main["start_date"] if main else None
    end = main["end_date"] if main else None
    days = (end - start).days + 1 if start and end else None
    months = period_months(days) if days is not None else None
    axes = {d["axis"] for c in parsed.contexts for d in json.loads(c["dimensions"])}
    return {
        "filing_id": filing["filing_id"],
        "symbol": filing["symbol"],
        "isin": filing["isin"],
        "taxonomy_version": taxonomy_version_from_href(parsed.schema_ref)
        or filing.get("taxonomy_version"),
        "file_path": filing["path"],
        "n_facts": len(all_facts),
        "n_numeric": sum(r["is_numeric"] for r in all_facts),
        "n_text": len(parsed.text_facts),
        "n_nil": sum(r["is_nil"] for r in all_facts),
        "n_concepts": len({(r["namespace"], r["concept"]) for r in all_facts}),
        "n_contexts": len(parsed.contexts),
        "n_units": len(parsed.units),
        "n_dimension_axes": len(axes),
        "main_context_id": main["context_id"] if main else None,
        "period_start": start,
        "period_end": end,
        "period_days": days,
        "period_months": months,
        "is_non_standard_period": None if months is None else months != 12,
        "parse_seconds": round(seconds, 3),
        "parser_version": PARSER_VERSION,
    }


# --- output --------------------------------------------------------------------------------------


def _partition_value(label: str) -> str:
    if not label or any(ch in label for ch in '/\\:=*?"<>|'):
        raise InstanceError(f"unusable {PARTITION_COL} {label!r}")
    return label


def remove_filing_outputs(filing_id: str, out_dir: Path) -> None:
    """Delete every Parquet file of ``filing_id`` (any partition) - keeps re-runs idempotent."""
    for table in TABLES:
        for path in (out_dir / table).glob(f"{PARTITION_COL}=*/{filing_id}.parquet"):
            path.unlink()


def write_parquet(parsed: ParsedInstance, filing_id: str, year_label: str, out_dir: Path) -> None:
    """Write ``out_dir/<table>/reporting_year_label=<label>/<filing_id>.parquet`` for each table.

    Previous files of this filing are removed first, so only this filing changes.
    """
    partition = f"{PARTITION_COL}={_partition_value(year_label)}"
    remove_filing_outputs(filing_id, out_dir)
    for table in TABLES:
        dest = out_dir / table / partition / f"{filing_id}.parquet"
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".parquet.tmp")
        pq.write_table(parsed.table(table), tmp, compression="zstd")
        tmp.replace(dest)


def _resolve_path(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else config.REPO_ROOT / p


def parse_filing(filing: dict, out_dir: Path) -> dict:
    """Parse one manifest row and write its tables; returns the filings row."""
    started = time.perf_counter()
    xml_path = _resolve_path(filing["path"])
    if not xml_path.is_file():
        raise FileNotFoundError(f"file not found: {filing['path']}")
    parsed = parse_instance(xml_path, filing["filing_id"])
    parsed.filings = [summarise(parsed, filing, time.perf_counter() - started)]
    write_parquet(parsed, filing["filing_id"], filing[PARTITION_COL], out_dir)
    return parsed.filings[0]


def _write_errors(errors_path: Path, new_rows: list[dict], reparsed_ids: set[str]) -> None:
    """Keep earlier errors of filings not re-parsed in this run; replace the rest."""
    rows: list[dict] = []
    if errors_path.exists():
        old = pd.read_csv(errors_path, dtype=str, keep_default_na=False)
        rows = [r for r in old.to_dict("records") if r["filing_id"] not in reparsed_ids]
    rows.extend(new_rows)
    errors_path.parent.mkdir(parents=True, exist_ok=True)
    with errors_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=ERROR_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def parse_all(
    manifest_path: Path = config.MANIFEST_PATH,
    out_dir: Path = config.PARSED_DIR,
    errors_path: Path = config.PARSE_ERRORS_CSV,
    only: str | None = None,
    limit: int | None = None,
) -> RunSummary:
    """Parse every manifest filing (optionally one symbol / the first N). Never stops on a file."""
    started = time.perf_counter()
    manifest = read_manifest(manifest_path)
    if only:
        manifest = manifest[manifest["symbol"].str.upper() == only.upper()]
    if limit is not None:
        manifest = manifest.head(limit)

    summary = RunSummary()
    for filing in manifest.to_dict("records"):
        try:
            row = parse_filing(filing, out_dir)
        except Exception as exc:  # one bad file must not stop the run
            remove_filing_outputs(filing["filing_id"], out_dir)
            summary.failed.append(
                {
                    "filing_id": filing["filing_id"],
                    "symbol": filing["symbol"],
                    PARTITION_COL: filing[PARTITION_COL],
                    "path": filing["path"],
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "logged_at": datetime.now(UTC).isoformat(timespec="seconds"),
                }
            )
            continue
        summary.parsed.append(row)
        summary.facts_by_taxonomy[row["taxonomy_version"]] += row["n_facts"]
        for key in ("n_facts", "n_numeric", "n_text", "n_contexts", "n_units"):
            summary.totals[key] += row[key]

    _write_errors(errors_path, summary.failed, set(manifest["filing_id"]))
    summary.seconds = time.perf_counter() - started
    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Parse BRSR XBRL filings into Parquet.")
    parser.add_argument("--only", metavar="SYMBOL", help="parse only this NSE symbol")
    parser.add_argument("--limit", type=int, metavar="N", help="parse only the first N filings")
    args = parser.parse_args(argv)

    s = parse_all(only=args.only, limit=args.limit)
    t = s.totals
    print(
        f"parse_xbrl: {len(s.parsed)} parsed, {len(s.failed)} failed in {s.seconds:.1f}s "
        f"-> {config.display_path(config.PARSED_DIR)}"
    )
    print(
        f"  facts={t['n_facts']:,} (numeric={t['n_numeric']:,}, text_facts={t['n_text']:,}) "
        f"contexts={t['n_contexts']:,} units={t['n_units']:,}"
    )
    for version, n in sorted(s.facts_by_taxonomy.items()):
        print(f"  taxonomy {version}: {n:,} facts")
    non_standard = [r for r in s.parsed if r["is_non_standard_period"] is not False]
    if non_standard:
        print(f"  {len(non_standard)} non-standard / unknown period(s):")
        for r in sorted(non_standard, key=lambda r: (r["symbol"], str(r["period_start"]))):
            print(
                f"    {r['symbol']:<12} {r['period_start']}..{r['period_end']} "
                f"({r['period_months']} months)"
            )
    for err in s.failed:
        print(f"  FAILED {err['symbol']} {err[PARTITION_COL]}: {err['error_type']}: {err['error']}")
    if s.failed:
        print(f"  errors -> {config.display_path(config.PARSE_ERRORS_CSV)}")


if __name__ == "__main__":
    main()
