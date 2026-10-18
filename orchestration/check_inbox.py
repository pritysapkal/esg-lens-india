"""First task of the pipeline: report what a person has saved into the inbox.

Never downloads and never moves anything (moving is the intake task's job). It fails only when
the raw data folder itself is missing, because then every later task would fail less clearly.

    python -m orchestration.check_inbox
"""

from __future__ import annotations

import sys

from ingestion import config


def main() -> int:
    if not config.RAW_DIR.exists():
        print(f"no raw data folder at {config.RAW_DIR}: set DATA_DIR", file=sys.stderr)
        return 1
    inbox = sorted(config.XBRL_INBOX_DIR.glob("*.xml")) if config.XBRL_INBOX_DIR.exists() else []
    filed = list(config.XBRL_DIR.rglob("*.xml")) if config.XBRL_DIR.exists() else []
    print(f"inbox: {len(inbox)} new XBRL file(s) in {config.XBRL_INBOX_DIR}")
    for path in inbox[:20]:
        print(f"  {path.name}")
    print(f"already filed: {len(filed)} XBRL file(s)")
    if not inbox:
        print("nothing new to file; the rest of the pipeline rebuilds from what is filed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
