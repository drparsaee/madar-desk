"""Real host -> independent store chain using disposable data, never Bridge.init."""
import tempfile
import threading
import unittest
from pathlib import Path

from native_app import Bridge
from standalone_accounting import AccountingRevisionConflict


class IndependentAccountingEndToEndTests(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory(prefix="madar-independent-e2e-")
        self.addCleanup(workspace.cleanup)
        self.root = Path(workspace.name)
        self.bridge = Bridge.__new__(Bridge)
        self.bridge.path = self.root / "tasks.json"
        self.bridge._lock = threading.RLock()
        self.bridge.connection = {"mode": "solo"}
        self.bridge.lan = None

    def command(self, typ, num, **kwargs):
        revision = self.bridge.standaloneAccountingRead()["revision"]
        return self.bridge.standaloneAccountingCommand({
            "expectedRevision": revision,
            "command": {"type": typ, "eventId": f"synthetic-{num}", **kwargs},
        })

    def test_local_bridge_real_store_is_independent(self):
        initial = self.bridge.standaloneAccountingRead()
        self.assertEqual(initial["revision"], 0)
        self.assertEqual(initial["view"]["currency"], "RIAL")
        self.command("party.register", 1,
                     partyId="vendor-one", name="Test Vendor", kind="vendor")
        self.command("bill.create", 2, billId="b-1", partyId="vendor-one",
                     documentDate="2026-01-01",
                     lines=[{"description": "Sample purchase", "quantity": 2,
                             "unitPrice": 300}])
        self.command("bill.approve", 3, billId="b-1")
        issued = self.command("bill.issue", 4, billId="b-1",
                              postingDate="2026-01-02")
        self.assertEqual(issued["view"]["parties"]["vendor-one"]["payable"], 600)
        self.assertEqual(issued["view"]["bills"]["b-1"]["status"], "issued")
        self.assertEqual(issued["revision"], 4)
        self.assertTrue((self.root / "standalone-accounting.sqlite3").is_file())
        for legacy in ("tasks.json", "finance.json", "madar-unified.sqlite3"):
            self.assertFalse((self.root / legacy).exists())

    def test_stale_or_client_supplied_actor_cannot_post(self):
        self.command("party.register", 1,
                     partyId="customer-one", name="Test Customer", kind="customer")
        with self.assertRaises(AccountingRevisionConflict):
            self.bridge.standaloneAccountingCommand({
                "command": {"type": "party.register", "eventId": "stale",
                            "partyId": "p2", "name": "Other", "kind": "customer"},
                "expectedRevision": 0,
            })
        with self.assertRaises(ValueError):
            self.bridge.standaloneAccountingCommand({
                "command": {"type": "party.register", "eventId": "spoof",
                            "partyId": "p3", "name": "Spoof", "kind": "customer"},
                "expectedRevision": 1, "actor": "local", "role": "admin",
            })
        self.assertEqual(self.bridge.standaloneAccountingRead()["revision"], 1)


if __name__ == "__main__":
    unittest.main()
