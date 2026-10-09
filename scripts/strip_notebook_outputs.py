"""Pre-commit hook: clear outputs and execution counts from Jupyter notebooks (stdlib only).

Notebooks here query real NSE-derived data, which must never be committed (docs/adr/0002).
Usage: python scripts/strip_notebook_outputs.py <file.ipynb> ...   Exit 1 if a file was changed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def strip(nb: dict) -> dict:
    for cell in nb.get("cells", []):
        if cell.get("cell_type") == "code":
            cell["outputs"] = []
            cell["execution_count"] = None
    return nb


def main(paths: list[str]) -> int:
    changed = 0
    for name in paths:
        path = Path(name)
        text = path.read_bytes().decode("utf-8")  # no newline translation: normalise to LF
        new = json.dumps(strip(json.loads(text)), indent=1, ensure_ascii=False) + "\n"
        if new != text:
            path.write_text(new, encoding="utf-8", newline="\n")
            print(f"stripped outputs: {name}")
            changed += 1
    return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
