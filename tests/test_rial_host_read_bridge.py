"""Isolated native/LAN read-only RIAL V2 host integration, never live APPDATA."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import json

import native_app
from lan import LanService
from ir_chart_model import ChartAccount, ChartSnapshot, PostingReference
from ir_journal_v2 import (
    FiscalPeriod, JournalSource, VerifiedScopes, JournalLine,
    new_journal_state, post_journal,
)
from ir_journal_sqlite import RIALJournalStorage
from money_policy import CompanyMoneyPolicy


def chart(company):
    return ChartSnapshot(company, accounts=(
        ChartAccount(company, "10", "KOL", None, "Assets", "asset"),
        ChartAccount(company, "1001", "MOEIN", "10", "Cash", "asset"),
        ChartAccount(company, "100101", "TAFSILI", "1001", "Cash leaf",
                     "asset", accountable=True),
        ChartAccount(company, "40", "KOL", None, "Revenue", "revenue"),
        ChartAccount(company, "4001", "MOEIN", "40", "Revenue", "revenue"),
        ChartAccount(company, "400101", "TAFSILI", "4001", "Revenue leaf",
                     "revenue", accountable=True),
    ))


class RIALHostReadBridgeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="madar-rial-bridge-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        env = patch.dict(os.environ, {"APPDATA": str(self.root),
                                       "LOCALAPPDATA": str(self.root)})
        env.start()
        self.addCleanup(env.stop)
        datadir = patch.object(native_app, "datadir", return_value=self.root)
        datadir.start()
        self.addCleanup(datadir.stop)
        self.bridge = native_app.Bridge()

    def _seed_rial(self):
        company = "company-A"
        base = new_journal_state(company, (
            FiscalPeriod(company, "FY26", "2026-01-01", "2026-12-31"),))
        storage = RIALJournalStorage(self.root / "madar-rial-v2.sqlite3")
        storage.commit(base, expected_revision=None)
        posted = post_journal(
            base, company_id=company, fiscal_period_id="FY26",
            event_id="synthetic-event-1", actor_id="synthetic-admin",
            posting_date="2026-10-21",
            source=JournalSource("independent", "synthetic-doc-1"),
            lines=(
                JournalLine(PostingReference(company, "100101"), debit_rial=1),
                JournalLine(PostingReference(company, "400101"), credit_rial=1),
            ),
            chart=chart(company),
            scopes=VerifiedScopes(independent_source_scopes=frozenset({
                ("", "synthetic-doc-1")})),
            money_policy=CompanyMoneyPolicy(company),
            expected_revision=base.revision, today="2026-10-21",
        )
        storage.commit(posted, expected_revision=base.revision)

    def test_missing_v2_does_not_import_or_create_old_finance(self):
        before = self.bridge._load_finance()
        with self.assertRaises(ValueError):
            self.bridge.rialJournalRead({
                "companyId": "company-A", "fiscalPeriodId": "FY26"})
        self.assertFalse((self.root / "madar-rial-v2.sqlite3").exists())
        self.assertEqual(self.bridge._load_finance(), before)

    def test_solo_read_only_exact_one_rial_and_missing_company(self):
        self._seed_rial()
        read = self.bridge.rialJournalRead({
            "companyId": "company-A", "fiscalPeriodId": "FY26"})
        self.assertEqual(read["schema"], "IR-JOURNAL-V2.1")
        self.assertEqual(read["currency"], "RIAL")
        self.assertEqual(read["companyId"], "company-A")
        self.assertEqual(len(read["journals"]), 1)
        self.assertEqual(read["journals"][0]["lines"][0]["debitRial"], "1")
        with self.assertRaises(ValueError):
            self.bridge.rialJournalRead({
                "companyId": "company-B", "fiscalPeriodId": "FY26"})
        with self.assertRaises(ValueError):
            self.bridge.rialJournalRead({
                "companyId": "company-A", "fiscalPeriodId": "OTHER"})

    def test_lan_read_denies_nonadmin_and_untrusted_or_missing_scope(self):
        self._seed_rial()
        server = LanService(self.bridge, self.root / "rial-users.json",
                            bind="127.0.0.1", port=0)
        server.setup_owner("admin", "strong-example-password")
        token = server.authenticate("admin", "strong-example-password")["token"]
        server.upsert_user(token, {
            "username": "editor", "password": "strong-editor-password",
            "role": "editor", "projects": []})
        editor = server.authenticate("editor", "strong-editor-password")["token"]
        request = {"companyId": "company-A", "fiscalPeriodId": "FY26"}
        with self.assertRaises(PermissionError):
            server.rial_journal_read(editor, request)
        with self.assertRaises(PermissionError):
            server.rial_journal_read("invalid-token", request)
        self.assertEqual(server.rial_journal_read(token, request)["journals"][0]
                         ["eventId"], "synthetic-event-1")
        for malformed in (
                {"companyId": "company-A", "fiscalPeriodId": "FY26",
                 "role": "admin"},
                {"companyId": "' OR 1=1 --", "fiscalPeriodId": "FY26"},
                {"companyId": "company-A", "fiscalPeriodId": []},
                {"companyId": "company-A"}):
            with self.subTest(malformed=malformed):
                with self.assertRaises(ValueError):
                    server.rial_journal_read(token, malformed)

    def test_client_does_not_offer_rial_posting(self):
        self.assertFalse(hasattr(self.bridge, "rialJournalCommand"))
        self.assertFalse(hasattr(self.bridge, "rialInvoiceIssuePreview"))

    def test_activation_requires_unified_storage_and_is_preserved_in_one_finance_snapshot(self):
        command = {"companyId": "company-A", "fiscalPeriodId": "FY26",
                   "startDate": "2026-01-01", "endDate": "2026-12-31"}
        with self.assertRaises(ValueError):
            self.bridge.rialJournalActivate(command)
        self.bridge.enableUnifiedStorage()
        old_finance = self.bridge._load_finance()
        out = self.bridge.rialJournalActivate(command)
        self.assertEqual(out["status"], "activated-empty-only")
        self.assertFalse(out["migrationPerformed"])
        current = self.bridge._load_finance()
        self.assertIn("rialJournalV2", current)
        self.assertEqual({k: v for k, v in current.items() if k != "rialJournalV2"},
                         old_finance)
        self.assertEqual(self.bridge.rialJournalRead({
            "companyId": "company-A", "fiscalPeriodId": "FY26"})["journals"], [])
        with self.assertRaises(ValueError):
            self.bridge.rialJournalActivate(command)

    def test_activation_denied_with_nonempty_legacy_finance_activity(self):
        self.bridge.enableUnifiedStorage()
        self.bridge.financeCommand({"type": "cost.toggle", "eventId": "legacy-toggle",
                                    "cardId": "example-2", "costEnabled": True})
        before = self.bridge._load_finance()
        with self.assertRaises(ValueError):
            self.bridge.rialJournalActivate({
                "companyId": "company-A", "fiscalPeriodId": "FY26",
                "startDate": "2026-01-01", "endDate": "2026-12-31"})
        self.assertEqual(self.bridge._load_finance(), before)

    def test_lan_admin_activation_and_editor_is_denied(self):
        self.bridge.enableUnifiedStorage()
        server = LanService(self.bridge, self.root / "activate-users.json",
                            bind="127.0.0.1", port=0)
        server.setup_owner("admin", "strong-example-password")
        admin = server.authenticate("admin", "strong-example-password")["token"]
        server.upsert_user(admin, {
            "username": "editor", "password": "strong-editor-password",
            "role": "editor", "projects": []})
        editor = server.authenticate("editor", "strong-editor-password")["token"]
        command = {"companyId": "company-A", "fiscalPeriodId": "FY26",
                   "startDate": "2026-01-01", "endDate": "2026-12-31"}
        with self.assertRaises(PermissionError):
            server.rial_journal_activate(editor, command)
        self.assertEqual(server.rial_journal_activate(admin, command)["currency"], "RIAL")
        self.assertEqual(server.rial_journal_read(admin, {
            "companyId": "company-A", "fiscalPeriodId": "FY26"})["journals"], [])

    def test_v2_unified_history_cannot_be_downgraded_by_old_client_or_restore(self):
        self.bridge.enableUnifiedStorage()
        self.bridge.rialJournalActivate({
            "companyId": "company-A", "fiscalPeriodId": "FY26",
            "startDate": "2026-01-01", "endDate": "2026-12-31"})
        store = self.bridge._unified_store
        head = store.load()
        with self.assertRaises(ValueError):
            store.restore(1, expected_revision=head.revision)
        old_client = head.bundle
        old_client["finance"].pop("rialJournalV2")
        with self.assertRaises(ValueError):
            store.commit(old_client, expected_revision=head.revision)
        current = store.load()
        self.assertEqual(current.revision, head.revision)
        self.assertIn("rialJournalV2", current.bundle["finance"])

    def test_http_rial_activation_is_admin_only_and_stays_empty(self):
        self.bridge.enableUnifiedStorage()
        server = LanService(self.bridge, self.root / "http-activate-users.json",
                            bind="127.0.0.1", port=0)
        server.setup_owner("admin", "strong-example-password")
        admin = server.authenticate("admin", "strong-example-password")["token"]
        server.upsert_user(admin, {
            "username": "viewer", "password": "strong-viewer-password",
            "role": "viewer", "projects": []})
        viewer = server.authenticate("viewer", "strong-viewer-password")["token"]
        port = server.start()
        self.addCleanup(server.stop)
        command = {"companyId": "company-A", "fiscalPeriodId": "FY26",
                   "startDate": "2026-01-01", "endDate": "2026-12-31"}
        endpoint = f"http://127.0.0.1:{port}/api/rial-journal/activate"

        def issue(token):
            req = Request(endpoint, data=json.dumps(command).encode("utf8"),
                          headers={"Authorization": "Bearer " + token,
                                   "Content-Type": "application/json"}, method="POST")
            try:
                with urlopen(req, timeout=5) as response:
                    return response.status, json.loads(response.read())
            except HTTPError as err:
                return err.code, json.loads(err.read())

        self.assertEqual(issue(viewer)[0], 403)
        self.assertEqual(issue("invalid")[0], 403)
        status, created = issue(admin)
        self.assertEqual(status, 200)
        self.assertFalse(created["result"]["migrationPerformed"])
        self.assertEqual(created["result"]["status"], "activated-empty-only")
        self.assertEqual(issue(admin)[0], 400)
        self.assertEqual(self.bridge.rialJournalRead({
            "companyId": "company-A", "fiscalPeriodId": "FY26"})["journals"], [])

    def test_lan_http_read_admin_only_and_no_post_route(self):
        self._seed_rial()
        server = LanService(self.bridge, self.root / "http-rial-users.json",
                            bind="127.0.0.1", port=0)
        server.setup_owner("admin", "strong-example-password")
        admin = server.authenticate("admin", "strong-example-password")["token"]
        server.upsert_user(admin, {
            "username": "viewer", "password": "strong-viewer-password",
            "role": "viewer", "projects": []})
        viewer = server.authenticate("viewer", "strong-viewer-password")["token"]
        port = server.start()
        self.addCleanup(server.stop)
        root = f"http://127.0.0.1:{port}/api/rial-journal"

        def request(token, suffix, method="GET", body=None):
            payload = None if body is None else json.dumps(body).encode("utf8")
            req = Request(root + suffix, data=payload,
                          headers={"Authorization": "Bearer " + token,
                                   "Content-Type": "application/json"},
                          method=method)
            try:
                with urlopen(req, timeout=5) as response:
                    return response.status, json.loads(response.read())
            except HTTPError as error:
                return error.code, json.loads(error.read())

        suffix = "?companyId=company-A&fiscalPeriodId=FY26"
        self.assertEqual(request(viewer, suffix)[0], 403)
        self.assertEqual(request("invalid", suffix)[0], 403)
        status, document = request(admin, suffix)
        self.assertEqual(status, 200)
        self.assertEqual(document["journals"][0]["lines"][0]["debitRial"], "1")
        self.assertEqual(request(admin, suffix + "&companyId=company-B")[0], 400)
        self.assertEqual(request(admin, suffix, method="POST", body={})[0], 405)


if __name__ == "__main__":
    unittest.main()
