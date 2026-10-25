"""R11 standalone startup, verified startup/exit backups, synthetic only."""
from __future__ import annotations
import json
import sys
from operational_r3_candidate_exe_qa import ROOT, FOLDER, exercise

def main():
    try:
        result=exercise(ROOT/'release'/'Madar-Accounting-Mohsen-UX-R11-20261025.exe',
                        'mohsen-r11-accounting',accounting=True)
        print(json.dumps(result,ensure_ascii=True,indent=2))
        return 0 if result['checks'] and all(result['checks'].values()) else 1
    finally:
        FOLDER.cleanup()

if __name__=='__main__':sys.exit(main())
