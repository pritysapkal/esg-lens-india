"""Find the SEBI BRSR taxonomy versions saved under ``data/raw/taxonomy``.

Folder layouts differ between packages (older ones nest an extra ``BRSR <version>`` folder),
so each version is located by searching for its entry schema ``in-capmkt-ent-<version>.xsd``
rather than by hard-coded paths. ``n_files`` counts the XBRL filings (inbox + intake store)
whose schemaRef points at that version.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from ingestion import config
from ingestion.instance import ENTRY_XSD_RE, InstanceError, read_header

TAXONOMY_COLUMNS = ["version", "path_to_entry_xsd", "n_files"]


def count_filings_by_version(xml_dirs: Iterable[Path]) -> Counter[str]:
    """Count XBRL instances per taxonomy version across ``xml_dirs`` (searched recursively)."""
    counts: Counter[str] = Counter()
    for xml_dir in xml_dirs:
        for path in sorted(xml_dir.rglob("*.xml")) if xml_dir.is_dir() else []:
            try:
                counts[read_header(path).taxonomy_version] += 1
            except InstanceError:
                continue
    return counts


def _entry_path(xsd: Path | None) -> str:
    return config.display_path(xsd) if xsd else ""


def find_taxonomies(
    taxonomy_dir: Path = config.TAXONOMY_DIR,
    xml_dirs: Iterable[Path] = (config.XBRL_INBOX_DIR, config.XBRL_DIR),
) -> pd.DataFrame:
    """Return one row per taxonomy version found on disk or referenced by a filing.

    A version referenced by filings but missing on disk gets an empty ``path_to_entry_xsd``.
    """
    entries: dict[str, Path] = {}
    for xsd in sorted(taxonomy_dir.rglob("in-capmkt-ent-*.xsd")):
        match = ENTRY_XSD_RE.search(xsd.name)
        if match:
            entries.setdefault(match.group(1), xsd)

    counts = count_filings_by_version(xml_dirs)
    rows = [
        {
            "version": version,
            "path_to_entry_xsd": _entry_path(entries.get(version)),
            "n_files": counts.get(version, 0),
        }
        for version in sorted(set(entries) | set(counts))
    ]
    return pd.DataFrame(rows, columns=TAXONOMY_COLUMNS)


def main() -> None:
    df = find_taxonomies()
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(config.TAXONOMY_VERSIONS_CSV, index=False, lineterminator="\n")
    print(df.to_string(index=False))
    missing = df.loc[df["path_to_entry_xsd"] == "", "version"].tolist()
    if missing:
        print(f"WARNING: filings use taxonomy versions not on disk: {missing}")
    print(f"-> {config.display_path(config.TAXONOMY_VERSIONS_CSV)}")


if __name__ == "__main__":
    main()
