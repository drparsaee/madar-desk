"""Actual local Bridge + unified SQLite purchase/RIAL integration, synthetic only."""
from copy import deepcopy
from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import native_app
from ir_finance_v2_extension import load_finance_rial_journal

SYNTHETIC_POSTING_DAY = datetime.now(timezone.utc).date().isoformat()


class SupplierRialHostTests(unittest.TestCase):
    def setUp(self):
        root = tempfile.TemporaryDirectory(prefix="madar-rial-purchase-isolated-")
        self.addCleanup(root.cleanup)
        self.root = Path(root.name)
        env = patch.dict(os.environ, {"APPDATA": str(self.root),
                                       "LOCALAPPDATA": str(self.root)})
        env.start()
        self.addCleanup(env.stop)
        safe_root = patch.object(native_app, "datadir", return_value=self.root)
        safe_root.start()
        self.addCleanup(safe_root.stop)
        self.bridge = native_app.Bridge()
        self.bridge.enableUnifiedStorage()
        task_data = self.bridge.getState()
        card = next(t for t in task_data["tasks"] if t["id"] == "example-2")
        card["checklist"].append(
            {"id": "vendor-stage", "text": "Synthetic carton cutting", "done": False})
        self.bridge.saveState(task_data)
        self.company = "company-qa"
        self.bridge.rialJournalActivate(
            {"companyId": self.company, "fiscalPeriodId": "FY2026",
             "startDate": "2026-01-01", "endDate": "2026-12-31"})

    def _stage(self):
        create = {"type": "intake.create", "eventId": "create",
                  "intakeId": "intake-card-step", "projectId": "p-sample",
                  "cardId": "example-2", "stepId": "vendor-stage",
                  "quantity": 7,
                  "supplier": {"id": "supplier-qa", "name": "Fake vendor",
                               "kind": "supplier", "reference": ""}}
        created = self.bridge.accountingCommand(create)
        self.assertEqual(created["bookedPayable"], 0)
        view = self.bridge.accountingRead("p-sample")
        self.assertEqual(view["documents"], [])
        self.bridge.accountingCommand(
            {"type": "intake.price", "eventId": "price",
             "intakeId": create["intakeId"], "unitPrice": 123})
        converted = self.bridge.accountingCommand(
            {"type": "intake.convert", "eventId": "convert",
             "intakeId": create["intakeId"]})
        self.assertEqual(converted["total"], 861)
        document = converted["documentId"]
        self.bridge.accountingCommand(
            {"type": "document.review", "eventId": "approve",
             "documentId": document, "projectId": "p-sample"})
        return document

    def test_real_bridge_stage_and_issue_is_one_atomic_sql_revision(self):
        document = self._stage()
        before = self.bridge._unified_store.load()
        command = {"type": "document.issue", "eventId": "issue-qa",
                   "documentId": document, "projectId": "p-sample",
                   "postingDate": SYNTHETIC_POSTING_DAY}
        result = self.bridge.accountingCommand(command)
        self.assertEqual(result["total"], 861)
        self.assertEqual(result["rialAmount"], "8610")
        after = self.bridge._unified_store.load()
        self.assertEqual(after.revision, before.revision + 1)
        v2 = load_finance_rial_journal(after.bundle["finance"], self.company)
        self.assertEqual(len(v2.events), 1)
        self.assertEqual(v2.events[-1].source.source_id, document)
        self.assertEqual(sum(x.debit_rial for x in v2.events[-1].lines), 8610)
        payable = next(x for x in self.bridge.accountingRead("p-sample")["balances"]
                       if x["partyId"] == "supplier-qa")
        self.assertEqual(payable["payable"], 861)
        retry = self.bridge.accountingCommand(command)
        self.assertEqual(retry, result)
        self.assertEqual(self.bridge._unified_store.load().revision, after.revision)
        with self.assertRaises((ValueError, PermissionError)):
            self.bridge.accountingCommand({**command, "eventId": "issue-other"})
        self.assertEqual(self.bridge._unified_store.load().revision, after.revision)

    def test_unpriced_and_cross_task_do_not_create_payable(self):
        self.bridge.accountingCommand(
            {"type": "intake.create", "eventId": "work",
             "intakeId": "intake-unpriced", "projectId": "p-sample",
             "cardId": "example-2", "stepId": "vendor-stage", "quantity": 2,
             "supplier": {"id": "supplier-qa", "name": "Fake vendor",
                          "kind": "supplier", "reference": ""}})
        old = self.bridge._unified_store.load()
        with self.assertRaises(ValueError):
            self.bridge.accountingCommand(
                {"type": "intake.convert", "eventId": "convert-unpriced",
                 "intakeId": "intake-unpriced"})
        self.assertEqual(self.bridge._unified_store.load().revision, old.revision)
        self.assertFalse(load_finance_rial_journal(
            self.bridge._load_finance(), self.company).events)


if __name__ == "__main__":
    unittest.main()
