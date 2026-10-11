"""Build the Leadership indicator seed from the SEBI BRSR taxonomies.

    python scripts/build_leadership_map.py           # rewrite the seed
    python scripts/build_leadership_map.py --check   # exit 1 if the seed is out of date

Output: dbt/seeds/leadership_indicator_map.csv.

BRSR has Essential (mandatory) and Leadership (voluntary) indicators. The taxonomy says which is
which: in the presentation linkbase of every version, each of the nine Principle roles has a node
``LeadershipIndicatorsAbstract``. Everything under that node is a Leadership element - nothing is
guessed from names.

One *indicator* = one direct child of that node (a question, or the heading of a table) together
with everything below it. The seed has one row per taxonomy version and reportable concept:

    taxonomy_version, principle, indicator, indicator_seq, concept, source

``indicator`` is the element name of the direct child; ``indicator_seq`` is its position under the
Leadership heading of its principle (the taxonomy's order, not SEBI's indicator number - SEBI
numbers some of these as parts a / b of one indicator). Left out: abstract headings, tables, axes
and members (they never carry a value), free "Notes" blocks, the "not applicable" explanation
elements and "is this applicable to the company" flags (saying that an indicator does not apply
is not an answer to it), and the assurance bookkeeping elements.

Needs the taxonomy packages under data/raw/taxonomy/<version>/ (not in git). The seed itself
holds element names only, no filed value.
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from collections import defaultdict
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingestion import config  # noqa: E402

SEED = config.DBT_DIR / "seeds" / "leadership_indicator_map.csv"
SEED_COLUMNS = ["taxonomy_version", "principle", "indicator", "indicator_seq", "concept", "source"]
LEADERSHIP_NODE = "LeadershipIndicatorsAbstract"
SOURCE = "presentation linkbase: descendants of LeadershipIndicatorsAbstract"

LINK = "{http://www.xbrl.org/2003/linkbase}"
XLINK = "{http://www.w3.org/1999/xlink}"
XSD = "{http://www.w3.org/2001/XMLSchema}"

# Elements under the Leadership heading that are not an answer to an indicator.
NOT_AN_ANSWER = re.compile(
    r"^Notes.*ExplanatoryTextBlock$"  # free notes on the principle
    r"|NotApplicable"  # the company's reason why an indicator does not apply
    r"|IsApplicableToTheCompany$"  # yes / no flag "does this indicator apply to us"
    r"|^AssuranceSubTypeFor|^RemarksForAssuranceOf|^TypeOfAssuranceFor|IsAssuredByAssurer$"
)


def _find_one(version_dir: Path, pattern: str) -> Path:
    matches = sorted(version_dir.rglob(pattern))
    if not matches:
        raise SystemExit(f"{pattern} not found under {version_dir}")
    return matches[0]


def reportable_concepts(version_dir: Path) -> set[str]:
    """Concepts of the core schema that can carry a value (not abstract, not a member)."""
    schema = etree.parse(str(_find_one(version_dir, "core/in-capmkt.xsd"))).getroot()
    names = set()
    for element in schema.iter(f"{XSD}element"):
        name = element.get("name")
        if not name or element.get("abstract") == "true":
            continue
        if "domainItemType" in (element.get("type") or ""):
            continue
        names.add(name)
    return names


def presentation_children(version_dir: Path, version: str) -> dict[str, dict[str, list[str]]]:
    """role -> parent concept -> children in presentation order."""
    linkbase = etree.parse(str(_find_one(version_dir, f"in-capmkt-pre-{version}.xml"))).getroot()
    roles: dict[str, dict[str, list[str]]] = {}
    for link in linkbase.iter(f"{LINK}presentationLink"):
        role = link.get(f"{XLINK}role").rsplit("/", 1)[-1]
        concept_of = {
            loc.get(f"{XLINK}label"): loc.get(f"{XLINK}href").rsplit("#in-capmkt_", 1)[-1]
            for loc in link.iter(f"{LINK}loc")
        }
        arcs: dict[str, list[tuple[float, str]]] = defaultdict(list)
        for arc in link.iter(f"{LINK}presentationArc"):
            parent = concept_of[arc.get(f"{XLINK}from")]
            arcs[parent].append((float(arc.get("order", "0")), concept_of[arc.get(f"{XLINK}to")]))
        roles[role] = {parent: [c for _, c in sorted(kids)] for parent, kids in arcs.items()}
    return roles


def _descendants(children: dict[str, list[str]], node: str) -> list[str]:
    found = []
    for child in children.get(node, []):
        found.append(child)
        found.extend(_descendants(children, child))
    return found


def build_rows(taxonomy_dir: Path = config.TAXONOMY_DIR) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for entry in sorted(taxonomy_dir.rglob("in-capmkt-ent-*.xsd")):
        version = entry.stem.replace("in-capmkt-ent-", "")
        version_dir = taxonomy_dir / version
        reportable = reportable_concepts(version_dir)
        for role, children in presentation_children(version_dir, version).items():
            if LEADERSHIP_NODE not in children:
                continue
            seq = 0
            for indicator in children[LEADERSHIP_NODE]:
                if NOT_AN_ANSWER.search(indicator):
                    continue
                concepts = [
                    concept
                    for concept in dict.fromkeys([indicator, *_descendants(children, indicator)])
                    if concept in reportable and not NOT_AN_ANSWER.search(concept)
                ]
                if not concepts:
                    continue
                seq += 1
                for concept in concepts:
                    rows.append(
                        {
                            "taxonomy_version": version,
                            "principle": role,
                            "indicator": indicator,
                            "indicator_seq": str(seq),
                            "concept": concept,
                            "source": SOURCE,
                        }
                    )
    return rows


def render(rows: list[dict[str, str]]) -> str:
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=SEED_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if the seed is out of date")
    args = parser.parse_args(argv)

    rows = build_rows()
    text = render(rows)
    summary: dict[str, tuple[set[str], int]] = {}
    for row in rows:
        indicators, n_concepts = summary.get(row["taxonomy_version"], (set(), 0))
        indicators.add(row["principle"] + "/" + row["indicator"])
        summary[row["taxonomy_version"]] = (indicators, n_concepts + 1)
    for version, (indicators, n_concepts) in sorted(summary.items()):
        print(f"{version}: {len(indicators)} Leadership indicators, {n_concepts} concepts")

    current = SEED.read_text(encoding="utf-8") if SEED.exists() else ""
    if args.check:
        if text != current:
            print(f"{SEED.name} is out of date: run python scripts/build_leadership_map.py")
            return 1
        return 0
    if text != current:
        SEED.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {config.display_path(SEED)} ({len(rows)} rows)")
    else:
        print(f"{config.display_path(SEED)} already up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
