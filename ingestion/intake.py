"""Manual-intake pipeline: file BRSR XBRL instances dropped into the inbox.

NSE's terms of use prohibit automated collection, so files are downloaded by hand and saved to
``data/raw/xbrl_inbox/``. This module never makes network requests. For each ``*.xml`` there:

1. compute sha256; read the entity identifier (``xbrli:identifier`` + scheme) and taxonomy
   version (schemaRef) with lxml;
2. match to the listing by exact ``xbrl_file_name`` (file names are never parsed for meaning);
3. resolve the ISIN (see below);
4. MOVE it to ``data/raw/xbrl/<ISIN>/<reporting_year_label>/<original name>``. Existing files
   are never overwritten: a different file with the same name gets a short-hash suffix;
5. append a row to ``data/raw/manifest.csv``.

ISIN resolution - only filings on taxonomy 2026-02-28 identify the entity by ISIN; older ones
use the CIN scheme (with dummy values for some companies, e.g. SBI). ``isin_source`` records
which rule applied, in order of preference:

- ``xbrl``: the filing's own identifier, when its scheme is ISIN;
- ``xbrl_same_symbol``: the ISIN from another filing of the same listing symbol (this run or
  the manifest) whose identifier scheme is ISIN;
- ``universe``: ``isin_code`` from the NIFTY 50 constituents list.

The raw identifier and its scheme are kept in the manifest either way.

Unmatched / unreadable files stay in the inbox and are reported. Files whose sha256 is already
in the manifest are left in the inbox and reported as duplicates, so a second run changes nothing.
"""

from __future__ import annotations

import csv
import hashlib
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from ingestion import config
from ingestion.discover import load_listings
from ingestion.instance import InstanceError, InstanceHeader, read_header
from ingestion.universe import load_universe

MANIFEST_COLUMNS: list[str] = [
    "filing_id",
    "symbol",
    "isin",
    "reporting_year_label",
    "taxonomy_version",
    "file_name",
    "sha256",
    "bytes",
    "received_at",
    "path",
    "matched_listing",
    "entity_identifier",
    "entity_identifier_scheme",
    "isin_source",
]


@dataclass
class IntakeResult:
    moved: list[dict] = field(default_factory=list)  # manifest rows written this run
    unmatched: list[tuple[str, str]] = field(default_factory=list)  # (file name, reason)
    duplicates: list[str] = field(default_factory=list)  # already received (same sha256)
    warnings: list[str] = field(default_factory=list)


@dataclass
class _Candidate:
    src: Path
    sha256: str
    filing: pd.Series
    header: InstanceHeader


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    """Return the SHA-256 hex digest of a file, read in chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def read_manifest(manifest_path: Path = config.MANIFEST_PATH) -> pd.DataFrame:
    """Return the manifest (empty frame with the right columns if it does not exist yet)."""
    if not manifest_path.exists():
        return pd.DataFrame(columns=MANIFEST_COLUMNS)
    return pd.read_csv(manifest_path, dtype=str, keep_default_na=False)


def _append_manifest(manifest_path: Path, row: dict) -> None:
    new_file = not manifest_path.exists()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANIFEST_COLUMNS, lineterminator="\n")
        if new_file:
            writer.writeheader()
        writer.writerow(row)


def _destination(dest_dir: Path, name: str, sha256: str) -> Path:
    """Original name if free; otherwise ``<stem>__<sha8><suffix>`` (never overwrites)."""
    dest = dest_dir / name
    if not dest.exists():
        return dest
    stem, suffix = Path(name).stem, Path(name).suffix
    for length in (8, 12, 16, 64):
        candidate = dest_dir / f"{stem}__{sha256[:length]}{suffix}"
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"no free destination for {name} in {dest_dir}")


def _universe_isins(universe: pd.DataFrame | None) -> dict[str, str]:
    """symbol -> isin_code from the constituents list (empty if unavailable)."""
    if universe is None:
        universe = load_universe() if config.UNIVERSE_CSV.exists() else pd.DataFrame()
    if universe.empty:
        return {}
    return dict(zip(universe["symbol"], universe["isin_code"], strict=True))


def _xbrl_isins(manifest: pd.DataFrame, batch: list[_Candidate]) -> dict[str, str]:
    """symbol -> ISIN from ISIN-scheme identifiers (manifest first, then this batch)."""
    isins: dict[str, str] = {}
    if len(manifest):
        received = manifest[manifest["isin_source"] == "xbrl"]
        for symbol, isin in zip(received["symbol"], received["isin"], strict=True):
            isins.setdefault(symbol, isin)
    for cand in batch:
        if cand.header.isin:
            isins.setdefault(cand.filing["symbol"], cand.header.isin)
    return isins


def intake(
    inbox_dir: Path = config.XBRL_INBOX_DIR,
    xbrl_dir: Path = config.XBRL_DIR,
    manifest_path: Path = config.MANIFEST_PATH,
    listing: pd.DataFrame | None = None,
    taxonomy_dir: Path = config.TAXONOMY_DIR,
    universe: pd.DataFrame | None = None,
) -> IntakeResult:
    """Move matched inbox files into the store and record them in the manifest."""
    if listing is None:
        listing = load_listings()
    by_name = {name: grp for name, grp in listing.groupby("xbrl_file_name")}
    manifest = read_manifest(manifest_path)
    known_sha = set(manifest["sha256"])
    result = IntakeResult()

    # Pass 1: identify every inbox file (read-only).
    batch: list[_Candidate] = []
    for src in sorted(inbox_dir.glob("*.xml")):
        sha = sha256_file(src)
        if sha in known_sha:
            result.duplicates.append(src.name)
            continue
        try:
            header = read_header(src)
        except InstanceError as exc:
            result.unmatched.append((src.name, str(exc)))
            continue
        rows = by_name.get(src.name)
        if rows is None:
            result.unmatched.append((src.name, "no listing row with this xbrl_file_name"))
            continue
        if len(rows) > 1:
            result.unmatched.append((src.name, f"{len(rows)} listing rows share this file name"))
            continue
        batch.append(_Candidate(src, sha, rows.iloc[0], header))

    xbrl_isins = _xbrl_isins(manifest, batch)
    universe_isins = _universe_isins(universe)
    for symbol, isin in sorted(xbrl_isins.items()):
        if symbol in universe_isins and universe_isins[symbol] != isin:
            result.warnings.append(
                f"{symbol}: ISIN in XBRL ({isin}) differs from the universe list "
                f"({universe_isins[symbol]})"
            )

    # Pass 2: resolve ISIN, move, record.
    for cand in batch:
        src, sha, filing, header = cand.src, cand.sha256, cand.filing, cand.header
        symbol = filing["symbol"]
        if header.isin:
            isin, isin_source = header.isin, "xbrl"
        elif symbol in xbrl_isins:
            isin, isin_source = xbrl_isins[symbol], "xbrl_same_symbol"
        elif symbol in universe_isins:
            isin, isin_source = universe_isins[symbol], "universe"
        else:
            reason = f"cannot resolve ISIN (identifier {header.identifier!r})"
            result.unmatched.append((src.name, reason))
            continue
        if sha in known_sha:  # identical copy earlier in this batch
            result.duplicates.append(src.name)
            continue

        if not (taxonomy_dir / header.taxonomy_version).is_dir():
            result.warnings.append(
                f"{src.name}: taxonomy {header.taxonomy_version} has no folder in "
                f"{config.display_path(taxonomy_dir)}"
            )  # still filed: the taxonomy can be added later

        dest_dir = xbrl_dir / isin / filing["reporting_year_label"]
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = _destination(dest_dir, src.name, sha)
        size = src.stat().st_size
        shutil.move(src, dest)

        row = {
            "filing_id": filing["filing_id"],
            "symbol": symbol,
            "isin": isin,
            "reporting_year_label": filing["reporting_year_label"],
            "taxonomy_version": header.taxonomy_version,
            "file_name": src.name,
            "sha256": sha,
            "bytes": size,
            "received_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "path": config.display_path(dest),
            "matched_listing": True,
            "entity_identifier": header.identifier,
            "entity_identifier_scheme": header.identifier_scheme,
            "isin_source": isin_source,
        }
        _append_manifest(manifest_path, row)
        known_sha.add(sha)
        result.moved.append(row)

    return result


def main() -> None:
    result = intake()
    print(f"intake: moved {len(result.moved)} file(s) -> {config.display_path(config.XBRL_DIR)}")
    sources = pd.Series([row["isin_source"] for row in result.moved]).value_counts()
    for source, n in sources.items():
        print(f"  isin_source={source}: {n}")
    if result.duplicates:
        print(f"  {len(result.duplicates)} already received (same sha256), left in inbox:")
        for name in result.duplicates:
            print(f"    {name}")
    if result.unmatched:
        print(f"  {len(result.unmatched)} unmatched, left in inbox:")
        for name, reason in result.unmatched:
            print(f"    {name}: {reason}")
    for warning in result.warnings:
        print(f"  WARNING: {warning}")


if __name__ == "__main__":
    main()
