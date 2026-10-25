"""One-time finalize an isolated trial ledger; no source financial journal posting.

Persist explicit RIAL currency in a zero-balance account.create event so the
test ledger cannot silently reopen as a legacy TOMAN revision-zero journal.
Create-only audit reports; refuses reruns.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from parsian_quarantine_stage import profile_export
from standalone_accounting import StandaloneAccountingStore


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--experiment", type=Path, required=True)
    cli.add_argument("--export", type=Path, required=True)
    args = cli.parse_args()
    root = args.experiment.absolute()
    if not root.is_dir() or root.is_symlink():
        raise RuntimeError("Invalid isolated trial folder")
    with args.export.open("r", encoding="utf-8") as file:
        data = json.load(file)
    profile = profile_export(data)
    store = StandaloneAccountingStore(
        root/"independent-madar-trial"/"standalone-accounting.sqlite3",
        default_currency="RIAL")
    actor = {
        "trial-auditor": {"username": "trial-auditor", "role": "admin"},
    }
    before = store.read(actor="trial-auditor", accounts=actor)
    if before["revision"] != 0 or before["view"]["journals"]:
        raise RuntimeError("Refusing to modify a nonempty trial ledger")
    event = {
        "type": "account.create",
        "eventId": "qa.parsian.initialized",
        "accountId": "qa.parsian.zero",
        "name": "Migration QA marker zero balance",
        "kind": "asset",
        "liquid": False,
    }
    store.command(event, actor="trial-auditor", accounts=actor,
                  expected_revision=0, now="2026-10-24T12:00:00Z")
    # Reopen explicitly as TOMAN to prove persisted currency wins over default.
    verified = StandaloneAccountingStore(
        store.path, default_currency="TOMAN").read(
            actor="trial-auditor", accounts=actor)
    if (verified["revision"] != 1 or
            verified["view"]["currency"] != "RIAL" or
            verified["view"]["journals"]):
        raise RuntimeError("Trial ledger currency persistence failed")
    summary = {
        "sourceFinancialPostingAllowed": profile["financialPostingAllowed"],
        "unbalancedDocumentGroups": profile["unbalancedDocumentGroups"],
        "orphanKolReferences": profile["orphanKolReferences"],
        "orphanMoeenReferences": profile["orphanMoeenReferences"],
        "orphanTafsiliReferences": profile["orphanTafsiliReferences"],
        "factorRowsWithoutMatchedJournalNumber": profile[
            "factorRowsWithoutMatchedJournalNumber"],
        "ledgerCurrencyPersisted": "RIAL",
        "nonfinancialSetupEvents": 1,
        "sourceFinancialJournalsPosted": 0,
        "trialLedgerFinancialJournals": 0,
        "sourceIsBackupSnapshot": False,
        "safeToReplaceParsian": False,
    }
    with (root/"read-only-source-audit.json").open("x", encoding="utf-8") as file:
        json.dump(profile, file, ensure_ascii=False, indent=2)
    with (root/"trial-ledger-currency-verification.json").open(
            "x", encoding="utf-8") as file:
        json.dump(summary, file, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
