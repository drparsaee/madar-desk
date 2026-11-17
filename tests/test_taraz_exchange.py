"""Task-only Madar contract with optional Taraz file proposals; isolated QA."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import native_app
from taraz_exchange import integration_status, queue_saved_task


def sample_state(currency="RIAL"):
    return {"tasks": [{
        "id": "task-1", "projectId": "project-1", "title": "Inspect cartons",
        "checklist": [{"id": "step-1", "expenseItems": [{
            "id": "expense-1", "quantity": 3, "unitPrice": 125,
            "currency": currency, "description": "Paper",
            "partyId": "private-vendor-1",
        }]}],
    }]}


class TarazExchangeTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="madar-taraz-qa-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        settings = patch.dict(os.environ, {
            "LOCALAPPDATA": str(self.root), "APPDATA": str(self.root)})
        settings.start()
        self.addCleanup(settings.stop)
        self.pending = self.root / "Madar-Taraz-Bridge" / "pending"

    def test_only_selected_saved_task_is_queued_without_financial_posting(self):
        saved = sample_state()
        result = queue_saved_task(saved, "task-1", "expense-1")
        self.assertEqual(result["postingPerformed"], False)
        self.assertEqual(len(list(self.pending.iterdir())), 1)
        file = self.pending / (result["id"] + ".json")
        record = json.loads(file.read_text(encoding="utf8"))
        self.assertEqual(record["schema"], 1)
        self.assertEqual(record["source"], "madar")
        self.assertEqual(record["taskId"], "task-1")
        self.assertEqual(record["title"], "Inspect cartons")
        self.assertEqual(record["projectId"], "project-1")
        self.assertEqual(record["expenseId"], "expense-1")
        self.assertEqual(record["amountRial"], "375")
        self.assertIn("createdUtc", record)
        self.assertNotIn("partyId", record)
        self.assertNotIn("description", record)
        self.assertEqual(len(record), 9)
        self.assertFalse((self.root / "MadarDesk").exists())
        self.assertFalse(any(self.pending.glob("*.tmp")))
        self.assertEqual(integration_status()["pending"], 1)

    def test_manual_task_proposal_omits_financial_fields(self):
        result = queue_saved_task(sample_state(), "task-1")
        record = json.loads((self.pending / (result["id"] + ".json")).read_text(encoding="utf8"))
        self.assertNotIn("expenseId", record)
        self.assertNotIn("amountRial", record)

    def test_unverified_currency_is_not_converted(self):
        result = queue_saved_task(sample_state("TOMAN"), "task-1", "expense-1")
        record = json.loads((self.pending / (result["id"] + ".json")).read_text(encoding="utf8"))
        self.assertEqual(record["expenseId"], "expense-1")
        self.assertNotIn("amountRial", record)

    def test_missing_task_or_expense_never_creates_file(self):
        for task_id, expense_id in [
            ("missing", None), ("task-1", "wrong"), ("../task-1", None),
        ]:
            with self.subTest(task_id=task_id, expense_id=expense_id):
                with self.assertRaises(ValueError):
                    queue_saved_task(sample_state(), task_id, expense_id)
        self.assertFalse(self.pending.exists())

    def test_retired_native_financial_methods_are_inaccessible(self):
        for method, args in [
            ("accountingRead", ()), ("accountingCommand", ({"type": "issue"},)),
            ("financeRead", ()), ("financeCommand", ({"type": "invoice.issue"},)),
            ("standaloneAccountingRead", ()),
            ("standaloneAccountingPrepare", ({"taskId": "task-1"},)),
            ("rialJournalActivate", ({},)),
        ]:
            with self.subTest(method=method):
                with self.assertRaises(PermissionError):
                    getattr(native_app.Bridge, method)(None, *args)

    def test_real_bridge_queues_only_saved_task_and_completion_has_no_finance_side_effect(self):
        bridge = native_app.Bridge()
        state = native_app.initial_state()
        bridge.saveState(state)
        task = next(item for item in state["tasks"] if item["id"] == "example-2")
        task["status"] = "done"
        bridge.saveState(state)
        self.assertFalse(bridge.finance_path.exists())
        self.assertFalse(bridge.finance_outbox_path.exists())
        prepared = bridge.tarazIntegrationPrepare("example-2")
        self.assertTrue(prepared["prepared"])
        queued = bridge.tarazIntegrationQueue("example-2", None, prepared["id"])
        self.assertTrue(queued["queued"])
        self.assertFalse(queued["postingPerformed"])
        self.assertEqual(json.loads(
            (self.pending / (queued["id"] + ".json")).read_text(encoding="utf8")
        )["taskId"], "example-2")
        with self.assertRaises(ValueError):
            bridge.tarazIntegrationPrepare("not-saved")


if __name__ == "__main__":
    unittest.main()
