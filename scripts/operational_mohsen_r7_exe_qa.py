"""Isolated EXE smoke of the new R7 accounting release candidate.

Checks a disposable standalone finance folder only. The installed Mohsensoft,
Parsian and R5/R6 user finance books are never opened.
"""
from __future__ import annotations

import json
import sys
from operational_r3_candidate_exe_qa import ROOT, FOLDER, exercise


def main():
    try:
        result = exercise(ROOT / "release" /
                          "Madar-Accounting-Mohsen-UX-R7-20261025.exe",
                          "mohsen-r7-accounting", accounting=True)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0 if result["checks"] and all(result["checks"].values()) else 1
    finally:
        FOLDER.cleanup()


if __name__ == "__main__":
    sys.exit(main())
