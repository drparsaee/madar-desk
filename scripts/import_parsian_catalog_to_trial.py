"""Safely populate only NON-FINANCIAL catalog rows into an isolated Madar trial.

This is NEVER a BAK import or a financial transaction migration.
Provenance: read-only live attached Parsian SQL, NOT the copied BAK snapshot.
All source prices, quantities, chart accounts and cash movements are ignored.
Items lacking a verified explicit unit are held in quarantine, not guessed.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from parsian_quarantine_stage import profile_export
from standalone_accounting import StandaloneAccountingStore

ACTOR = {"trial-auditor": {"username": "trial-auditor", "role": "admin"}}


def _valid_text(value, *, limit):
    return (type(value) is str and 0 < len(value.strip()) <= limit
            and not any(ord(c) < 32 or ord(c) == 127 for c in value))


def _source_catalog(export):
    profile_export(export)
    goods = export["tables"]["tbl_Goods"]
    commands, deferred = [], []
    seen = set()
    for row in goods:
        value = row["Code"]
        if type(value) not in (int, float, str):
            raise ValueError("Invalid item code type")
        try:
            code = Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError("Unusable item code") from exc
        if (not code.is_finite() or code < 0 or
                code >= 2**53 or code != code.to_integral_value()):
            raise ValueError("Unstable non-whole legacy item code")
        raw_code = str(int(code))
        if raw_code in seen:
            raise ValueError("Duplicate source item code")
        seen.add(raw_code)
        name = row["CName"]
        if not _valid_text(name, limit=300):
            raise ValueError("Unusable source item name")
        unit = row["UnitName_1"]
        if not _valid_text(unit, limit=40):
            deferred.append(raw_code)
            continue
        uid = sha256(raw_code.encode("ascii")).hexdigest()[:24]
        commands.append({
            "type": "item.create",
            "eventId": "qa.goods.event." + uid,
            "itemId": "qa.goods." + uid,
            "sku": "PARS-" + raw_code,
            "name": name.strip(),
            "kind": "goods",
            "unit": unit.strip(),
        })
    return commands, deferred


def import_to_trial(export_path, experiment):
    root = Path(experiment).absolute()
    expected = root/"independent-madar-trial"/"standalone-accounting.sqlite3"
    quarantine = root/"parsian-source-quarantine.sqlite3"
    if (root.is_symlink() or not root.is_dir() or
            not expected.is_file() or not quarantine.is_file() or
            not root.name.startswith("migration-experiment-")):
        raise ValueError("Only the previously isolated MADAR trial is accepted")
    data = Path(export_path).read_bytes()
    export = json.loads(data.decode("utf-8"))
    with sqlite3.connect(quarantine) as db:
        recorded_hash = db.execute(
            "SELECT value FROM metadata WHERE key='source_export_sha256'"
        ).fetchone()[0]
        posting = db.execute(
            "SELECT value FROM metadata WHERE key='financial_posting_allowed'"
        ).fetchone()[0]
    if recorded_hash != sha256(data).hexdigest() or posting != "false":
        raise ValueError("Source export differs from validated quarantine")
    commands, deferred = _source_catalog(export)
    store = StandaloneAccountingStore(expected, default_currency="RIAL")
    starting = store.read(actor="trial-auditor", accounts=ACTOR)
    if (starting["revision"] != 1 or
            starting["view"]["currency"] != "RIAL" or
            starting["view"]["journals"] or
            starting["view"]["items"]):
        raise ValueError("Refusing to import into a used or unverified ledger")
    for index, command in enumerate(commands):
        store.command(command, actor="trial-auditor", accounts=ACTOR,
                      expected_revision=index+1, now="2026-10-24T12:00:00Z")
    completed = StandaloneAccountingStore(expected, default_currency="TOMAN").read(
        actor="trial-auditor", accounts=ACTOR)
    if (completed["revision"] != 1 + len(commands) or
            len(completed["view"]["items"]) != len(commands) or
            completed["view"]["journals"] or
            completed["view"]["currency"] != "RIAL"):
        raise RuntimeError("Madar trial catalog post-import validation failed")
    summary = {
        "status": "SOURCE_CATALOG_IN_TRIAL_NOT_FINANCIAL_MIGRATION",
        "sourceRecordType": "ATTACHED_LIVE_SQL_NOT_COPIED_BACKUP",
        "sourceGoods": len(export["tables"]["tbl_Goods"]),
        "catalogItemsAdded": len(commands),
        "catalogItemsDeferredMissingUnit": len(deferred),
        "remainingStockQuantitiesImported": 0,
        "itemPricesImported": 0,
        "sourceFinancialJournalsPosted": 0,
        "madarTrialFinancialJournals": 0,
        "trialCurrency": completed["view"]["currency"],
        "trialRevision": completed["revision"],
        "sourceCurrencyVerified": False,
        "bakSnapshotEquivalenceVerified": False,
        "productionDataModified": False,
    }
    with (root/"trial-catalog-import-status.json").open(
            "x", encoding="utf-8") as file:
        json.dump(summary, file, ensure_ascii=False, indent=2)
    return summary


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--experiment", required=True)
    cli.add_argument("--export", required=True)
    args = cli.parse_args()
    print(json.dumps(import_to_trial(args.export, args.experiment),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
