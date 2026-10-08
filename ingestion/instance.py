"""Lightweight reads of a BRSR XBRL instance: header (ISIN, taxonomy version) and size counts.

The header is read with ``iterparse`` and stops at the first entity identifier, so it is cheap
enough to run on every file in the inbox. Nothing here interprets the file *name* - naming
patterns differ between years, so all metadata comes from the XML content.

The entity identifier is NOT always an ISIN. Observed in the NIFTY 50 filings:
taxonomy 2026-02-28 uses scheme ``.../in-capmkt/ISIN``; older taxonomies use
``.../in-capmkt/CorporateIdentityNumber`` (a CIN, or a dummy value for companies without one,
e.g. SBI). ``InstanceHeader.isin`` is therefore set only for the ISIN scheme.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

XBRLI_NS = "http://www.xbrl.org/2003/instance"
LINK_NS = "http://www.xbrl.org/2003/linkbase"
XLINK_NS = "http://www.w3.org/1999/xlink"
XSI_NIL = "{http://www.w3.org/2001/XMLSchema-instance}nil"

SCHEMA_REF_TAG = f"{{{LINK_NS}}}schemaRef"
IDENTIFIER_TAG = f"{{{XBRLI_NS}}}identifier"
CONTEXT_TAG = f"{{{XBRLI_NS}}}context"
UNIT_TAG = f"{{{XBRLI_NS}}}unit"

# Entry schema of the SEBI capital-markets taxonomy, e.g. in-capmkt-ent-2026-02-28.xsd
ENTRY_XSD_RE = re.compile(r"in-capmkt-ent-(\d{4}-\d{2}-\d{2})\.xsd$")
ISIN_RE = re.compile(r"^IN[A-Z0-9]{9}[0-9]$")


class InstanceError(ValueError):
    """The file is not a readable BRSR XBRL instance."""


@dataclass(frozen=True)
class InstanceHeader:
    identifier: str  # xbrli:identifier value, exactly as filed
    identifier_scheme: str  # last path segment of the scheme URI, e.g. "ISIN"
    taxonomy_version: str
    schema_ref: str

    @property
    def isin(self) -> str | None:
        """The identifier if it is an ISIN-scheme, ISIN-shaped value; otherwise None."""
        if self.identifier_scheme == "ISIN" and ISIN_RE.match(self.identifier):
            return self.identifier
        return None


@dataclass(frozen=True)
class InstanceCounts:
    facts: int
    concepts: int
    contexts: int
    units: int
    nil_facts: int


def taxonomy_version_from_href(href: str) -> str | None:
    """Return the taxonomy version (YYYY-MM-DD) from a schemaRef href, or None."""
    match = ENTRY_XSD_RE.search(href.strip().replace("\\", "/"))
    return match.group(1) if match else None


def read_header(path: Path) -> InstanceHeader:
    """Read the schemaRef href and the first ``xbrli:identifier`` (with scheme) of an instance."""
    schema_ref: str | None = None
    identifier: str | None = None
    scheme = ""
    try:
        for _, elem in etree.iterparse(str(path), events=("end",), huge_tree=True):
            if elem.tag == SCHEMA_REF_TAG and schema_ref is None:
                schema_ref = elem.get(f"{{{XLINK_NS}}}href", "")
            elif elem.tag == IDENTIFIER_TAG:
                identifier = (elem.text or "").strip()
                scheme = elem.get("scheme", "").rstrip("/").rsplit("/", 1)[-1]
                break
    except etree.XMLSyntaxError as exc:
        raise InstanceError(f"{path.name}: not well-formed XML ({exc})") from exc

    if not schema_ref:
        raise InstanceError(f"{path.name}: no link:schemaRef found")
    if not identifier:
        raise InstanceError(f"{path.name}: no xbrli:identifier found")
    version = taxonomy_version_from_href(schema_ref)
    if version is None:
        raise InstanceError(f"{path.name}: unrecognised schemaRef href {schema_ref!r}")
    return InstanceHeader(
        identifier=identifier,
        identifier_scheme=scheme,
        taxonomy_version=version,
        schema_ref=schema_ref,
    )


def count_instance(path: Path) -> InstanceCounts:
    """Count facts, distinct concepts, contexts, units and nil facts in an instance.

    A fact is any top-level child of ``xbrli:xbrl`` outside the xbrli / link namespaces.
    """
    root = etree.parse(str(path), parser=etree.XMLParser(huge_tree=True)).getroot()
    facts = [
        el
        for el in root
        if isinstance(el.tag, str) and etree.QName(el).namespace not in (XBRLI_NS, LINK_NS)
    ]
    return InstanceCounts(
        facts=len(facts),
        concepts=len({el.tag for el in facts}),
        contexts=len(root.findall(CONTEXT_TAG)),
        units=len(root.findall(UNIT_TAG)),
        nil_facts=sum(el.get(XSI_NIL) == "true" for el in facts),
    )
