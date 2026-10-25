"""Host purchase/RIAL adversarial QA against synthetic local SQLite only.

Uses the EXISTING native integration test's isolated Bridge fixture: APPDATA,
LOCALAPPDATA and datadir are redirected into TemporaryDirectory, and no LAN
listener is started. No real finance, database or application files are used.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_rial_purchase_host_integration as fixtures
from accounting_service import apply_madar_accounting
from app_storage import RevisionConflict, UnifiedAppStorage
from ir_finance_v2_extension import load_finance_rial_journal
from ir_purchase_host_adapter import issue_supplier_purchase_with_rial
from lan import LanService
from money_policy import snapshot_sha256
from purchase_intake import apply_intake

COMPANY = "company-qa"
PROJECT = "p-sample"
CARD = "example-2"
STEP = "vendor-stage"
INTAKE = "intake-card-step"
VENDOR = "supplier-qa"
ISSUE = "issue-adversarial"


def issue_intent(bill, event=ISSUE):
    return {"type": "document.issue", "eventId": event,
            "documentId": bill, "projectId": PROJECT,
            "postingDate": fixtures.SYNTHETIC_POSTING_DAY}


class PurchaseHostAdversarialTests(unittest.TestCase):
    # Invoke existing tested fixture, not its TestCase subclass (avoids
    # rerunning inherited unrelated tests). Fixture registers all cleanups.
    setUp = fixtures.SupplierRialHostTests.setUp
    _stage = fixtures.SupplierRialHostTests._stage

    def authoritative_context(self, actor="local", accounts=None):
        data = self.bridge.getState()
        if accounts is None:
            accounts = self.bridge._solo_collab_context()[0]
        return {"actor": actor, "accounts": accounts,
                "cards": data["tasks"], "projects": data["projects"],
                "now": fixtures.SYNTHETIC_POSTING_DAY + "T23:00:00Z"}

    def persist(self, finance, *, expected=None):
        head = self.bridge._unified_store.load()
        return self.bridge._unified_store.commit(
            {**head.bundle, "finance": finance},
            expected_revision=head.revision if expected is None else expected)

    def _open_priced_intake(self):
        self.bridge.accountingCommand({
            "type": "intake.create", "eventId": "intake-open", "intakeId": "intake-open",
            "projectId": PROJECT, "cardId": CARD, "stepId": STEP, "quantity": 2,
            "supplier": {"id": VENDOR, "name": "Fake vendor",
                         "kind": "supplier", "reference": ""}})
        self.bridge.accountingCommand({
            "type": "intake.price", "eventId": "price-valid",
            "intakeId": "intake-open", "unitPrice": 123})
        return self.bridge._unified_store.load()

    def _assert_priced_forgery_rejected(self, before, forged):
        with self.assertRaises((ValueError, PermissionError)):
            self.persist(forged)
        current = self.bridge._unified_store.load()
        self.assertEqual(current.bundle, before.bundle)
        self.assertEqual(current.revision, before.revision)
        self.assertTrue(self.bridge._unified_store.integrity_check())

    def test_tampered_converted_price_and_vendor_rejected_at_sql_guard(self):
        bill = self._stage()
        baseline = self.bridge._unified_store.load()
        for mutation in ("unitPrice", "supplierName", "supplierId"):
            forged = deepcopy(baseline.bundle["finance"])
            row = forged["purchaseIntakes"]["records"][INTAKE]
            if mutation == "unitPrice":
                row["unitPrice"] += 1
            elif mutation == "supplierName":
                row["supplier"]["name"] = "Different Vendor"
            else:
                row["supplier"]["id"] = "evil-supplier"
            with self.subTest(mutation=mutation):
                with self.assertRaises((ValueError, PermissionError)):
                    self.persist(forged)
                self.assertEqual(self.bridge._unified_store.load().revision,
                                 baseline.revision)
        self.assertEqual(self.bridge._unified_store.load().bundle,
                         baseline.bundle)
        result = self.bridge.accountingCommand(issue_intent(bill))
        self.assertEqual(result["total"], 861)
        self.assertEqual(result["rialAmount"], "8610")

    def test_host_intake_price_command_cannot_smuggle_supplier_or_actor(self):
        # Create a new intake but do not price it, then attack the exposed
        # accountingCommand API instead of the persistence object.
        self.bridge.accountingCommand({
            "type": "intake.create", "eventId": "unpriced-extra",
            "intakeId": "unpriced-extra", "projectId": PROJECT, "cardId": CARD,
            "stepId": STEP, "quantity": 3,
            "supplier": {"id": VENDOR, "name": "Fake vendor",
                         "kind": "supplier", "reference": ""}})
        baseline = self.bridge._unified_store.load()
        for key, val in (("supplier", {"id": "attacker"}), ("actor", "admin"),
                         ("scopes", ["p-all"])):
            with self.subTest(field=key):
                with self.assertRaises((ValueError, PermissionError)):
                    self.bridge.accountingCommand({
                        "type": "intake.price", "eventId": "smuggled-" + key,
                        "intakeId": "unpriced-extra", "unitPrice": 999,
                        key: val})
        self.assertEqual(self.bridge._unified_store.load().revision, baseline.revision)
        self.assertEqual(self.bridge.accountingRead(PROJECT)["purchaseIntakes"][-1]["unitPrice"], None)

    def test_native_alternate_issue_event_and_replay_are_not_double_posted(self):
        bill = self._stage()
        command = issue_intent(bill)
        initial = self.bridge._unified_store.load()
        issued = self.bridge.accountingCommand(command)
        head = self.bridge._unified_store.load()
        self.assertEqual(head.revision, initial.revision + 1)
        self.assertEqual(issued["rialAmount"], "8610")
        self.assertEqual(self.bridge.accountingCommand(command), issued)
        self.assertEqual(self.bridge._unified_store.load().revision, head.revision)
        with self.assertRaises((ValueError, PermissionError)):
            self.bridge.accountingCommand(issue_intent(bill, "alternate-issue"))
        self.assertEqual(self.bridge._unified_store.load().revision, head.revision)
        self.assertEqual(len(load_finance_rial_journal(
            head.bundle["finance"], COMPANY).events), 1)

    def test_raw_legacy_issue_cannot_bypass_rial_in_sql_snapshot(self):
        bill = self._stage()
        head = self.bridge._unified_store.load()
        old = apply_madar_accounting(
            head.bundle["finance"], issue_intent(bill),
            **self.authoritative_context())["state"]
        with self.assertRaises((ValueError, PermissionError)):
            self.persist(old)
        self.assertEqual(self.bridge._unified_store.load().revision, head.revision)
        self.assertTrue(self.bridge._unified_store.integrity_check())

    def test_finance_hash_and_integer_revision_cas_refuse_stale_commit(self):
        bill = self._stage()
        before = self.bridge._unified_store.load()
        candidate = issue_supplier_purchase_with_rial(
            before.bundle["finance"], issue_intent(bill),
            **self.authoritative_context())["state"]
        # Intervening legitimate nonposting accounting mutation advances
        # authoritative finance independently of the stale candidate.
        self.bridge.accountingCommand({
            "type": "party.register", "eventId": "fresh-source",
            "partyId": "supplier-another", "name": "Other Vendor",
            "kind": "vendor"})
        current = self.bridge._unified_store.load()
        self.assertEqual(current.revision, before.revision + 1)
        with self.assertRaisesRegex(RuntimeError, "CONFLICT"):
            self.bridge._commit_domain("finance", candidate,
                                       expected_finance_sha256=snapshot_sha256(
                                           before.bundle["finance"]))
        with self.assertRaises(RevisionConflict):
            self.persist(candidate, expected=before.revision)
        self.assertEqual(self.bridge._unified_store.load().revision, current.revision)
        self.assertEqual(self.bridge._unified_store.load().bundle, current.bundle)

    def test_sql_failure_after_insert_rolls_back_both_purchase_and_rial(self):
        bill = self._stage()
        previous = self.bridge._unified_store.load()
        original = UnifiedAppStorage._insert

        def crash_after_write(cls, connection, raw, current, source):
            original(connection, raw, current, source)
            raise OSError("synthetic failure after revision/header write")

        with patch.object(UnifiedAppStorage, "_insert",
                          classmethod(crash_after_write)):
            with self.assertRaisesRegex(OSError, "synthetic failure"):
                self.bridge.accountingCommand(issue_intent(bill))
        head = self.bridge._unified_store.load()
        self.assertEqual(head.bundle, previous.bundle)
        self.assertEqual(head.revision, previous.revision)
        self.assertTrue(self.bridge._unified_store.integrity_check())
        issued = self.bridge.accountingCommand(issue_intent(bill))
        self.assertEqual(issued["rialAmount"], "8610")
        self.assertEqual(self.bridge._unified_store.load().revision, previous.revision + 1)

    def test_lan_editor_grant_and_spoofed_fields_denied_without_commit(self):
        service = LanService(self.bridge, self.root / "adversarial-users.json")
        service.setup_owner("owner", "OwnerPassword-2026!")
        owner_token = service.authenticate("owner", "OwnerPassword-2026!")["token"]
        service.upsert_user(owner_token, {
            "username": "editor", "role": "editor", "projects": [PROJECT],
            "password": "EditorPassword-2026!"})
        service.users["editor"]["financeEdit"] = True
        editor = service.authenticate("editor", "EditorPassword-2026!")["token"]
        bill = self._stage()
        initial = self.bridge._unified_store.load()
        with self.assertRaises((PermissionError, ValueError)):
            service.accounting_command(editor, issue_intent(bill))
        with self.assertRaises(PermissionError):
            service.accounting_command("forged-token", issue_intent(bill))
        for field, value in (("actor", "owner"), ("companyId", COMPANY),
                             ("proof", {"trusted": True})):
            with self.subTest(field=field), self.assertRaises((ValueError, PermissionError)):
                service.accounting_command(
                    owner_token, {**issue_intent(bill), field: value})
        self.assertEqual(self.bridge._unified_store.load().revision, initial.revision)
        # The trusted LAN admin path successfully routes the matching issue.
        result = service.accounting_command(owner_token, issue_intent(bill))
        self.assertEqual(result["rialAmount"], "8610")
        after = self.bridge._unified_store.load()
        self.assertEqual(after.revision, initial.revision + 1)
        self.assertEqual(service.accounting_command(owner_token, issue_intent(bill)), result)
        self.assertEqual(self.bridge._unified_store.load().revision, after.revision)

    def test_persisted_priced_intake_can_be_rewritten_with_forged_receipt(self):
        """A formatted but fake intake receipt must NOT justify a price edit."""
        before = self._open_priced_intake()
        forged = deepcopy(before.bundle["finance"])
        forged["purchaseIntakes"]["records"]["intake-open"]["unitPrice"] = 999
        forged["purchaseIntakes"]["receipts"]["injected"] = {
            "fingerprint": "0" * 64, "result": {"proposedTotal": 1998}}
        self._assert_priced_forgery_rejected(before, forged)

    def test_priced_change_without_new_receipt_refused(self):
        before = self._open_priced_intake()
        forged = deepcopy(before.bundle["finance"])
        forged["purchaseIntakes"]["records"]["intake-open"]["unitPrice"] = 999
        self._assert_priced_forgery_rejected(before, forged)

    def test_priced_change_with_wrong_event_receipt_refused(self):
        before = self._open_priced_intake()
        forged = deepcopy(before.bundle["finance"])
        forged["purchaseIntakes"]["records"]["intake-open"]["unitPrice"] = 999
        unrelated = {"type": "intake.price", "eventId": "wrong-event",
                     "intakeId": "some-other-intake", "unitPrice": 999}
        digest = sha256(json.dumps(unrelated, sort_keys=True,
                                   ensure_ascii=False, separators=(",", ":"),
                                   allow_nan=False).encode("utf8")).hexdigest()
        forged["purchaseIntakes"]["receipts"]["wrong-event"] = {
            "fingerprint": digest,
            "result": {"intakeId": "intake-open", "status": "priced",
                       "proposedTotal": 1998, "bookedPayable": 0}}
        self._assert_priced_forgery_rejected(before, forged)

    def test_priced_change_with_wrong_receipt_result_refused(self):
        before = self._open_priced_intake()
        forged = deepcopy(before.bundle["finance"])
        forged["purchaseIntakes"]["records"]["intake-open"]["unitPrice"] = 999
        command = {"type": "intake.price", "eventId": "wrong-result",
                   "intakeId": "intake-open", "unitPrice": 999}
        digest = sha256(json.dumps(command, sort_keys=True, ensure_ascii=False,
                                   separators=(",", ":"), allow_nan=False
                                   ).encode("utf8")).hexdigest()
        forged["purchaseIntakes"]["receipts"]["wrong-result"] = {
            "fingerprint": digest, "result": {"proposedTotal": 999}}
        self._assert_priced_forgery_rejected(before, forged)

    def test_unrelated_or_extra_receipt_cannot_reauthorize_price(self):
        before = self._open_priced_intake()
        for mode in ("unrelated", "multiple"):
            with self.subTest(mode=mode):
                forged = deepcopy(before.bundle["finance"])
                forged["purchaseIntakes"]["records"]["intake-open"]["unitPrice"] = 999
                if mode == "unrelated":
                    command = {"type": "intake.cancel", "eventId": "other-kind",
                               "intakeId": "intake-open"}
                    forged["purchaseIntakes"]["receipts"]["other-kind"] = {
                        "fingerprint": sha256(json.dumps(
                            command, sort_keys=True, ensure_ascii=False,
                            separators=(",", ":"), allow_nan=False
                        ).encode("utf8")).hexdigest(),
                        "result": {"intakeId": "intake-open", "status": "cancelled",
                                   "bookedPayable": 0}}
                else:
                    for eid in ("receipt-one", "receipt-two"):
                        forged["purchaseIntakes"]["receipts"][eid] = {
                            "fingerprint": "0" * 64, "result": {"ignored": True}}
                self._assert_priced_forgery_rejected(before, forged)

    def test_even_exact_unkeyed_command_digest_and_result_cannot_direct_commit(self):
        """Regression for the residual bypass previously demonstrated."""
        before = self._open_priced_intake()
        forged = deepcopy(before.bundle["finance"])
        state = forged["purchaseIntakes"]
        forged["purchaseIntakes"] = apply_intake(
            state, {"type": "intake.price", "eventId": "forged-full-replay",
                    "intakeId": "intake-open", "unitPrice": 999},
            cards=[], projects=[], now=state["records"]["intake-open"]["updatedAt"]
        )["state"]
        # All three pieces (updated price, fingerprint, result) would have
        # passed the prior replay-only check. No authenticated host command.
        self._assert_priced_forgery_rejected(before, forged)

    def test_legitimate_reprice_cancel_and_issue_still_follow_host_reducer(self):
        self.bridge.accountingCommand({
            "type": "intake.create", "eventId": "original", "intakeId": "open",
            "projectId": PROJECT, "cardId": CARD, "stepId": STEP,
            "quantity": 3,
            "supplier": {"id": VENDOR, "name": "Fake vendor",
                         "kind": "supplier", "reference": ""}})
        first = self.bridge.accountingCommand({
            "type": "intake.price", "eventId": "pricing-1",
            "intakeId": "open", "unitPrice": 123})
        second = self.bridge.accountingCommand({
            "type": "intake.price", "eventId": "pricing-2",
            "intakeId": "open", "unitPrice": 321})
        self.assertEqual(first["proposedTotal"], 369)
        self.assertEqual(second["proposedTotal"], 963)
        canceled = self.bridge.accountingCommand({
            "type": "intake.cancel", "eventId": "cancellation",
            "intakeId": "open"})
        self.assertEqual(canceled["bookedPayable"], 0)
        self.assertEqual(self.bridge.accountingRead(PROJECT)["purchaseIntakes"][-1]["status"],
                         "cancelled")
        self.assertEqual(len(load_finance_rial_journal(
            self.bridge._load_finance(), COMPANY).events), 0)
        # The same commercial work may be opened again after cancellation.
        self.bridge.accountingCommand({
            "type": "intake.create", "eventId": "replacement",
            "intakeId": "replacement", "projectId": PROJECT,
            "cardId": CARD, "stepId": STEP, "quantity": 2,
            "supplier": {"id": VENDOR, "name": "Fake vendor",
                         "kind": "supplier", "reference": ""}})
        self.bridge.accountingCommand({
            "type": "intake.price", "eventId": "replacement-price",
            "intakeId": "replacement", "unitPrice": 111})
        converted = self.bridge.accountingCommand({
            "type": "intake.convert", "eventId": "replacement-convert",
            "intakeId": "replacement"})
        self.bridge.accountingCommand({
            "type": "document.review", "eventId": "replacement-approve",
            "documentId": converted["documentId"], "projectId": PROJECT})
        issued = self.bridge.accountingCommand(
            issue_intent(converted["documentId"], "replacement-issue"))
        self.assertEqual(issued["total"], 222)
        self.assertEqual(issued["rialAmount"], "2220")
        self.assertEqual(len(load_finance_rial_journal(
            self.bridge._load_finance(), COMPANY).events), 1)


if __name__ == "__main__":
    unittest.main()
