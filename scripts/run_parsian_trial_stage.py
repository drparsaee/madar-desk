"""Run a create-only, separated test ledger plus NON-POSTING raw-source quarantine.

All input/output paths are explicit. The SQL source was already exported with
scripts/parsian_live_readonly_stage.ps1; this script does not connect to SQL.
It never makes accounting entries from unverified Parsian records.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3

from parsian_quarantine_stage import create_quarantine
from standalone_accounting import StandaloneAccountingStore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--backup-copy", type=Path, required=True)
    args = parser.parse_args()
    root = args.experiment.absolute()
    if not root.is_dir() or root.is_symlink():
        raise RuntimeError("Experiment destination must be an existing separate directory")
    quarantine = root / "parsian-source-quarantine.sqlite3"
    report = create_quarantine(args.export, quarantine,
                               backup_copy=args.backup_copy)
    ledger_root = root / "independent-madar-trial"
    ledger_root.mkdir(exist_ok=False)
    store = StandaloneAccountingStore(
        ledger_root / "standalone-accounting.sqlite3", default_currency="RIAL")
    state = store.read(actor="trial-auditor", accounts={
        "trial-auditor": {"username": "trial-auditor", "role": "admin"},
    })
    assert state["revision"] == 0
    assert state["view"]["currency"] == "RIAL"
    assert len(state["view"]["journals"]) == 0
    with sqlite3.connect(quarantine) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM raw_source_rows").fetchone()[0]
        flag = conn.execute(
            "SELECT value FROM metadata WHERE key=?", (
                "financial_posting_allowed",)).fetchone()[0]
        if flag != "false" or conn.execute(
                "PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Staged source integrity check failed")
    summary = {
        "status": "SOURCE_QUARANTINED_NOT_POSTED",
        "dataCameFrom": "ATTACHED_LIVE_SQL_READ_ONLY_NOT_BAK_SNAPSHOT",
        "sourceRecords": count,
        "sourceJournalGroups": report["documentGroups"],
        "unbalancedSourceGroups": report["unbalancedDocumentGroups"],
        "orphanKolReferences": report["orphanKolReferences"],
        "orphanMoeenReferences": report["orphanMoeenReferences"],
        "orphanTafsiliReferences": report["orphanTafsiliReferences"],
        "factorRowsWithoutMatchedJournalNumber": report[
            "factorRowsWithoutMatchedJournalNumber"],
        "sourceCurrencyVerified": False,
        "backupSnapshotMatchVerified": False,
        "financialPostingAllowed": False,
        "standaloneTrialLedgerCurrency": state["view"]["currency"],
        "standaloneTrialLedgerRevision": state["revision"],
        "standaloneTrialJournalCount": len(state["view"]["journals"]),
        "canReplaceParsian": False,
    }
    with (root / "trial-stage-status.json").open("x", encoding="utf-8") as file:
        json.dump(summary, file, ensure_ascii=False, sort_keys=True, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
