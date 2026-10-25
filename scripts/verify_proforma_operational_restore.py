"""Offline restore acceptance of the COMPLETED synthetic WebView sales workflow."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
scratch = ROOT/".qa-proforma-live-gui-20261024"
finance = scratch/"financial"
report = scratch/"restore-report.json"
if not finance.is_dir() or not (scratch/"operational-report.json").is_file():
    raise SystemExit("Required synthetic GUI run is missing")
sys.path.insert(0,str(ROOT))
from standalone_accounting import StandaloneAccountingStore
from standalone_accounting_restore import (
    restore_standalone_accounting, _check_input,
)

accounts = {"auditor":{"username":"auditor","role":"admin"}}
backups = sorted((finance/"standalone-accounting-backups").glob("*.sqlite3"),
                 key=lambda p:p.stat().st_mtime_ns)
checks = {}
latest = backups[-1]
dest_parent = scratch/"offline-restored"
dest_parent.mkdir(exist_ok=False)
destination = dest_parent/"standalone-accounting.sqlite3"
before = _check_input(latest)
created = restore_standalone_accounting(
    latest,destination,offline_acknowledged=True,plaintext_acknowledged=True)
checks["restore_created_new_file"]=created==destination and destination.is_file()
restored = StandaloneAccountingStore(destination).read(
    actor="auditor",accounts=accounts)
original = StandaloneAccountingStore(finance/"standalone-accounting.sqlite3").read(
    actor="auditor",accounts=accounts)
checks["same_revision"]=restored["revision"]==original["revision"]==8
checks["same_view"]=restored["view"]==original["view"]
checks["original_not_overwritten"]=(finance/"standalone-accounting.sqlite3").is_file()
checks["proforma_invoice_receipt_preserved"]=(
    restored["view"]["proformas"]["qa.proforma"]["status"]=="converted" and
    restored["view"]["invoices"]["qa.invoice"]["status"]=="issued" and
    restored["view"]["parties"]["qa.customer"]["receivable"]==500 and
    len(restored["view"]["journals"])==2
)
try:
    restore_standalone_accounting(
        latest,destination,offline_acknowledged=True,plaintext_acknowledged=True)
    checks["destination_no_clobber"]=False
except FileExistsError:
    checks["destination_no_clobber"]=True

tampered = scratch/"tampered-fixture.sqlite3"
shutil.copyfile(latest,tampered)
with sqlite3.connect(tampered) as conn:
    conn.execute("UPDATE standalone_accounting SET digest=? WHERE id=1",
                 ("0"*64,))
try:
    _check_input(tampered)
    checks["corrupt_backup_rejected"]=False
except Exception:
    checks["corrupt_backup_rejected"]=True

report.write_text(json.dumps({"checks":checks,
    "head_revision":before[0],"source":str(latest),
    "restored":str(created)},indent=2,ensure_ascii=False),encoding="utf8")
print(json.dumps(checks,ensure_ascii=False))
sys.exit(0 if all(checks.values()) else 1)
