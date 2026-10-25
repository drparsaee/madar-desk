"""Execute R4 GUI+backup smoke only in synthetic temp directories.

Uses the established R3 safety harness but references only new, distinct R4
files. The baseline R2/R3 installations and all real APPDATA are untouched.
"""
from __future__ import annotations

import json
import sys
from operational_r3_candidate_exe_qa import ROOT, FOLDER, exercise


def main():
    results = []
    try:
        for label, filename, accounting in (
            ("r4-accounting", "Madar-Accounting-Fixes-R4-20261025.exe", True),
            ("r4-main", "Madar-Desk-Fixes-R4-20261025.exe", False),
        ):
            results.append(exercise(ROOT / "release" / filename, label,
                                    accounting=accounting))
        print(json.dumps(results, ensure_ascii=True, indent=2))
        return 0 if all(row["checks"] and all(row["checks"].values())
                        for row in results) else 1
    finally:
        FOLDER.cleanup()


if __name__ == "__main__":
    sys.exit(main())
