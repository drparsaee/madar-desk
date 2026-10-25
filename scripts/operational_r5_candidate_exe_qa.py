"""Safety-isolated R5 GUI and mandatory backup smoke for both new EXE names."""
from __future__ import annotations

import json
import sys
from operational_r3_candidate_exe_qa import ROOT, FOLDER, exercise


def main():
    results = []
    try:
        for label, filename, accounting in (
            ("r5-accounting", "Madar-Accounting-Fixes-R5-20261025.exe", True),
            ("r5-main", "Madar-Desk-Fixes-R5-20261025.exe", False),
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
