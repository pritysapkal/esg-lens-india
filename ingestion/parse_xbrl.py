"""Parse BRSR XBRL instance documents into Parquet tables (lxml, streaming-friendly).

Planned behaviour (implemented in a later week - this is a stub):

One instance file (~2,000 facts, ~618 concepts, ~658 contexts, 35 dimension axes,
~11 units) is flattened into four Parquet tables under ``data/processed/``:

- ``contexts``   : filing_id, context_id, entity identifier, period type, start/end/instant
                   date, and one row per (context_id, axis, member) for dimensional contexts.
- ``units``      : filing_id, unit_id, measure(s) incl. divide numerator/denominator
                   (INR, pure, GJ, t, tCO2e, kl, per-rupee ratios ...).
- ``facts``      : numeric facts - filing_id, concept (QName + namespace), context_ref,
                   unit_ref, decimals, ``value_raw`` (string, exactly as filed), nil flag.
- ``text_facts`` : non-numeric facts (text blocks, enumerations, dates), ``value_raw``.

Rules:
- **Keep raw string values** (``value_raw``); casting to numbers happens in dbt staging.
- Record ``taxonomy_version`` (from schemaRef, e.g. 2026-02-28) on every row so
  concept mappings stay taxonomy-version aware.
- Each file contains current-year AND prior-year values; keep both (period columns
  distinguish them) - they feed the restatement tracker.
- Company key = ISIN (from the entity identifier); input files come from the intake store
  ``data/raw/xbrl/<ISIN>/<reporting_year_label>/`` (see ``ingestion.intake``).

Test data: ``tests/fixtures/synthetic_brsr.xml`` (synthetic). Real-data tests use HDFC Bank
FY2025-26 from the local intake store (2,182 facts, 618 concepts, 658 contexts, 11 units) and
skip when it is absent - real filings are never committed.
"""

from __future__ import annotations

from pathlib import Path


def parse_instance(xml_path: Path) -> dict:
    """Parse one XBRL instance and return {table_name: DataFrame} for the four tables."""
    raise NotImplementedError("parse_instance is planned for week 3")


def write_parquet(tables: dict, out_dir: Path) -> None:
    """Write parsed tables to ``out_dir/<table>.parquet`` (append / partition by filing)."""
    raise NotImplementedError("write_parquet is planned for week 3")


def main() -> None:
    raise NotImplementedError("parse_xbrl is planned for week 3")


if __name__ == "__main__":
    main()
