"""Isolated smoke of new packaged R6 accounting with original FR3-derived UI."""
from __future__ import annotations

import json
from pathlib import Path
import sys

from operational_r3_candidate_exe_qa import ROOT, FOLDER, exercise


def main():
    try:
        r = exercise(ROOT / "release" /
                     "Madar-Accounting-Parsian-Karma-R6-20261025.exe",
                     "r6-parsian-karma-accounting", accounting=True)
        print(json.dumps(r, ensure_ascii=True, indent=2))
        return 0 if r["checks"] and all(r["checks"].values()) else 1
    finally:
        FOLDER.cleanup()


if __name__ == "__main__":
    sys.exit(main())
