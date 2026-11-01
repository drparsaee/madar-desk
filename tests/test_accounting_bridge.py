"""Host integration of task->sale and cost->purchase accounting in isolated roots."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import native_app
from lan import LanService


def sale():
    return {"type": "draft.sales.fromTask", "eventId": "host-sale-v1",
            "projectId": "p-sample", "cardId": "example-2",
            "party": {"id": "sara", "name": "Sara", "reference": "", "kind": "customer"},
            "lines": [{"id": "printing", "description": "Box printing",
                       "quantity": 1, "unitPrice": 1500}],
            "discount": 0, "tax": 0, "advance": 0}


def buy():
    return {"type": "draft.purchase.fromCosts", "eventId": "host-bill-v1",
            "projectId": "p-sample",
            "party": {"id": "vendor1", "name": "Paper vendor", "reference": "",
                      "kind": "supplier"},
            "selections": [{"cardId": "example-2", "sourceId": "direct"}],
            "basis": "estimated", "approveEstimate": True}


class AccountingBridgeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="madar-acc-host-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        environment = patch.dict(os.environ, {"APPDATA": str(self.root),
                                             "LOCALAPPDATA": str(self.root)})
        environment.start()
        self.addCleanup(environment.stop)
        patched = patch.object(native_app, "datadir", return_value=self.root)
        patched.start()
        self.addCleanup(patched.stop)
        self.bridge = native_app.Bridge()
        self.bridge.saveState(native_app.initial_state())
        state = self.bridge.getState()
        selected = next(t for t in state["tasks"] if t["id"] == "example-2")
        selected.update({"cost": 500, "costEnabled": True})
        self.bridge.saveState(state)

    def _do(self, cmd):
        return self.bridge.accountingCommand(cmd)

    def test_named_person_sale_and_vendor_purchase_survive_legacy_reopen(self):
        sale_id = self._do(sale())["documentId"]
        bill_id = self._do(buy())["documentId"]
        self.assertNotEqual(sale_id, bill_id)
        snap = self.bridge.accountingRead("p-sample")
        self.assertEqual(len(snap["documents"]), 2)
        self.assertEqual({d["status"] for d in snap["documents"]}, {"Draft"})
        restarted = native_app.Bridge()
        self.assertEqual(len(restarted.accountingRead("p-sample")["documents"]), 2)
        self.assertEqual(len(restarted.getState()["tasks"]), len(self.bridge.getState()["tasks"]))
        self.assertTrue(json.loads(self.bridge.finance_path.read_text("utf8"))["accounting"]["events"])

    def test_sale_and_purchase_balances_only_arise_from_issued_documents(self):
        sid = self._do(sale())["documentId"]
        bid = self._do(buy())["documentId"]
        self.assertEqual(sum(b["receivable"] + b["payable"] for b in
                             self.bridge.accountingRead("p-sample")["balances"]), 0)
        for ident, name in ((sid, "sale"), (bid, "bill")):
            self._do({"type": "document.review", "eventId": "review-" + name,
                      "documentId": ident, "projectId": "p-sample"})
            self._do({"type": "document.issue", "eventId": "issue-" + name,
                      "documentId": ident, "projectId": "p-sample",
                      "postingDate": datetime.now(timezone.utc).date().isoformat()})
        view = self.bridge.accountingRead("p-sample")
        self.assertEqual(next(x for x in view["balances"] if x["partyId"] == "sara")["receivable"], 1500)
        self.assertEqual(next(x for x in view["balances"] if x["partyId"] == "vendor1")["payable"], 500)
        self.assertTrue(self.bridge.financeRead("p-sample") == [])

    def test_accounting_invoice_state_persists_in_opt_in_unified_sqlite(self):
        self.bridge.enableUnifiedStorage()
        self._do(sale())
        self._do(buy())
        restarted = native_app.Bridge()
        self.assertEqual(len(restarted.accountingRead("p-sample")["documents"]), 2)
        self.assertTrue(restarted._unified_store.integrity_check())
        self.assertTrue((self.root / "madar-unified.sqlite3").is_file())

    def test_lan_role_is_checked_for_read_and_create(self):
        server = LanService(self.bridge, self.root / "users.json", bind="127.0.0.1", port=0)
        server.setup_owner("admin", "strong-example-password")
        admin = server.authenticate("admin", "strong-example-password")["token"]
        server.upsert_user(admin, {"username": "editor", "password": "strong-editor-password",
                                   "role": "editor", "projects": ["p-sample"]})
        editor = server.authenticate("editor", "strong-editor-password")["token"]
        with self.assertRaises(PermissionError):
            server.accounting_read(editor, "p-sample")
        with self.assertRaises(PermissionError):
            server.accounting_command(editor, sale())
        self.assertEqual(server.accounting_command(admin, sale())["total"], 1500)
        self.assertEqual(len(server.accounting_read(admin, "p-sample")["documents"]), 1)

    def test_duplicate_event_is_not_double_posted(self):
        first = self._do(sale())
        second = self._do(sale())
        self.assertEqual(first, second)
        self.assertEqual(len(self.bridge.accountingRead("p-sample")["documents"]), 1)

    def test_loopback_http_rejects_viewer_and_requires_named_admin_authority(self):
        server = LanService(self.bridge, self.root / "http-users.json",
                            bind="127.0.0.1", port=0)
        server.setup_owner("admin", "strong-example-password")
        admin = server.authenticate("admin", "strong-example-password")["token"]
        server.upsert_user(admin, {"username": "viewer", "password": "strong-viewer-password",
                                   "role": "viewer", "projects": ["p-sample"]})
        viewer = server.authenticate("viewer", "strong-viewer-password")["token"]
        port = server.start()
        self.addCleanup(server.stop)
        base = f"http://127.0.0.1:{port}/api/accounting"

        def request(token, command=None):
            raw = None if command is None else json.dumps(command).encode("utf8")
            req = Request(base + "?projectId=p-sample" if command is None else base,
                          data=raw,
                          headers={"Authorization": "Bearer " + token,
                                   "Content-Type": "application/json"},
                          method="GET" if command is None else "POST")
            try:
                with urlopen(req, timeout=4) as response:
                    return response.status, json.loads(response.read())
            except HTTPError as err:
                return err.code, json.loads(err.read())

        self.assertEqual(request(viewer)[0], 403)
        self.assertEqual(request(viewer, sale())[0], 403)
        self.assertEqual(request("invalid")[0], 403)
        status, created = request(admin, sale())
        self.assertEqual(status, 200)
        self.assertEqual(created["result"]["total"], 1500)
        status, view = request(admin)
        self.assertEqual(status, 200)
        self.assertEqual(len(view["documents"]), 1)
        self.assertEqual(view["documents"][0]["party"]["name"], "Sara")


if __name__ == "__main__":
    unittest.main()
