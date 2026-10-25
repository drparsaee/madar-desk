"""P0 authenticated intake CAS: only synthetic Bridge/SQLite, never real APPDATA."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_rial_purchase_host_integration as fixtures
from app_storage import RevisionConflict, UnifiedAppStorage
from ir_finance_v2_extension import load_finance_rial_journal
from lan import LanService
from money_policy import snapshot_sha256
from purchase_intake import apply_intake

PROJECT = "p-sample"
CARD = "example-2"
STEP = "vendor-stage"
VENDOR = {"id": "supplier-qa", "name": "Fake vendor",
          "kind": "supplier", "reference": ""}


class AuthenticatedIntakeCASTests(unittest.TestCase):
    setUp = fixtures.SupplierRialHostTests.setUp
    _stage = fixtures.SupplierRialHostTests._stage

    def _create(self, *, event="create-auth", intake="intake-auth"):
        return self.bridge.accountingCommand({
            "type": "intake.create", "eventId": event, "intakeId": intake,
            "projectId": PROJECT, "cardId": CARD, "stepId": STEP,
            "quantity": 2, "supplier": deepcopy(VENDOR)})

    def _current(self):
        return self.bridge._unified_store.load()

    def _raw(self, finance):
        current = self._current()
        return self.bridge._unified_store.commit(
            {**current.bundle, "finance": finance},
            expected_revision=current.revision)

    def test_red_fully_consistent_forged_intake_price_cannot_direct_commit(self):
        self._create()
        self.bridge.accountingCommand({
            "type": "intake.price", "eventId": "real-price",
            "intakeId": "intake-auth", "unitPrice": 123})
        before = self._current()
        forged = deepcopy(before.bundle["finance"])
        old = forged["purchaseIntakes"]
        # The hostile caller constructs the EXACT valid receipt from the pure
        # reducer: digest, event and result are self-consistent, but this is NOT
        # a host-authenticated price command.
        forged["purchaseIntakes"] = apply_intake(
            old, {"type": "intake.price", "eventId": "forged-price",
                  "intakeId": "intake-auth", "unitPrice": 999},
            cards=[], projects=[], now=old["records"]["intake-auth"]["updatedAt"]
        )["state"]
        with self.assertRaises((ValueError, PermissionError)):
            self._raw(forged)
        self.assertEqual(self._current().revision, before.revision)
        self.assertEqual(self._current().bundle, before.bundle)

    def test_direct_public_commit_rejects_legitimate_intake_snapshot_too(self):
        old = self._current()
        from accounting_service import apply_madar_accounting
        intent = {"type": "intake.create", "eventId": "direct-create",
                  "intakeId": "direct", "projectId": PROJECT, "cardId": CARD,
                  "stepId": STEP, "quantity": 2, "supplier": deepcopy(VENDOR)}
        new = apply_madar_accounting(old.bundle["finance"], intent,
                                     actor="local",
                                     accounts=self.bridge._solo_collab_context()[0],
                                     cards=old.bundle["tasks"]["tasks"],
                                     projects=old.bundle["tasks"]["projects"],
                                     now="2026-10-22T10:00:00Z")["state"]
        with self.assertRaises((ValueError, PermissionError)):
            self._raw(new)
        self.assertEqual(self._current().revision, old.revision)

    def test_native_authenticated_create_price_reprice_cancel(self):
        initial = self._current()
        self._create()
        self.bridge.accountingCommand({
            "type": "intake.price", "eventId": "price-one",
            "intakeId": "intake-auth", "unitPrice": 123})
        self.bridge.accountingCommand({
            "type": "intake.price", "eventId": "price-two",
            "intakeId": "intake-auth", "unitPrice": 321})
        self.bridge.accountingCommand({
            "type": "intake.cancel", "eventId": "cancel-one",
            "intakeId": "intake-auth"})
        after = self._current()
        self.assertEqual(after.revision, initial.revision + 4)
        self.assertEqual(after.bundle["finance"]["purchaseIntakes"]
                         ["records"]["intake-auth"]["status"], "cancelled")
        self.assertEqual(after.bundle["finance"]["purchaseIntakes"]
                         ["records"]["intake-auth"]["unitPrice"], 321)
        self.assertFalse(load_finance_rial_journal(
            after.bundle["finance"], "company-qa").events)

    def test_authenticated_exact_retry_never_increments_revision(self):
        request = {"type": "intake.create", "eventId": "retry-create",
                   "intakeId": "retry-intake", "projectId": PROJECT,
                   "cardId": CARD, "stepId": STEP, "quantity": 2,
                   "supplier": deepcopy(VENDOR)}
        response = self.bridge.accountingCommand(request)
        after = self._current()
        self.assertEqual(self.bridge.accountingCommand(request), response)
        self.assertEqual(self._current().revision, after.revision)
        with self.assertRaises((ValueError, PermissionError)):
            self.bridge.accountingCommand({**request, "quantity": 3})
        self.assertEqual(self._current().revision, after.revision)

    def test_native_authenticated_conversion_review_joint_issue(self):
        bill = self._stage()
        issued_before = self._current()
        issue = {"type": "document.issue", "eventId": "issue-auth",
                 "documentId": bill, "projectId": PROJECT,
                 "postingDate": fixtures.SYNTHETIC_POSTING_DAY}
        result = self.bridge.accountingCommand(issue)
        self.assertEqual(result["rialAmount"], "8610")
        self.assertEqual(self._current().revision, issued_before.revision + 1)
        self.assertEqual(self.bridge.accountingCommand(issue), result)
        self.assertEqual(self._current().revision, issued_before.revision + 1)

    def test_authenticated_intake_precondition_and_revision_conflicts(self):
        before = self._current()
        command = {"type": "intake.create", "eventId": "cas-create",
                   "intakeId": "cas-intake", "projectId": PROJECT,
                   "cardId": CARD, "stepId": STEP, "quantity": 1,
                   "supplier": deepcopy(VENDOR)}
        context = {"actor": "local", "accounts": self.bridge._solo_collab_context()[0],
                   "now": "2026-10-22T10:00:00Z",
                   "expected_finance_sha256": snapshot_sha256(before.bundle["finance"])}
        self._create(event="intervening", intake="other-intake")
        newer = self._current()
        with self.assertRaises(RevisionConflict):
            self.bridge._unified_store.commit_authenticated_intake(
                command, expected_revision=before.revision, **context)
        with self.assertRaisesRegex((ValueError, RuntimeError), "CONFLICT"):
            self.bridge._unified_store.commit_authenticated_intake(
                command, expected_revision=newer.revision, **context)
        self.assertEqual(self._current().revision, newer.revision)

    def test_independent_storage_handles_one_cas_winner_under_race(self):
        before = self._current()
        digest = snapshot_sha256(before.bundle["finance"])
        context = {"actor": "local", "accounts": self.bridge._solo_collab_context()[0],
                   "now": "2026-10-22T10:00:00Z",
                   "expected_revision": before.revision,
                   "expected_finance_sha256": digest}

        def write_one(number):
            other = UnifiedAppStorage(self.bridge._unified_store.path)
            command = {"type": "intake.create", "eventId": "race-" + str(number),
                       "intakeId": "race-" + str(number),
                       "projectId": PROJECT, "cardId": CARD, "stepId": STEP,
                       "quantity": 1, "supplier": deepcopy(VENDOR)}
            try:
                return ("ok", other.commit_authenticated_intake(
                    command, **context)["revision"])
            except RevisionConflict:
                return ("conflict", None)

        with ThreadPoolExecutor(max_workers=2) as pool:
            completed = list(pool.map(write_one, (1, 2)))
        self.assertEqual(sorted(row[0] for row in completed), ["conflict", "ok"])
        self.assertEqual(self._current().revision, before.revision + 1)
        self.assertEqual(len(self._current().bundle["finance"]
                             ["purchaseIntakes"]["records"]), 1)
        self.assertTrue(self.bridge._unified_store.integrity_check())

    def test_restore_cannot_reintroduce_old_intake_state(self):
        self._create()
        head = self._current()
        with self.assertRaises((ValueError, PermissionError)):
            self.bridge._unified_store.restore(
                head.revision - 1, expected_revision=head.revision)
        self.assertEqual(self._current().revision, head.revision)

    def test_host_intake_failure_after_insert_rolls_back(self):
        before = self._current()
        original = UnifiedAppStorage._insert

        def fail_after_insert(cls, connection, raw, current, source):
            original(connection, raw, current, source)
            raise OSError("synthetic failure after staged intake SQL insert")

        with patch.object(UnifiedAppStorage, "_insert",
                          classmethod(fail_after_insert)):
            with self.assertRaisesRegex(OSError, "synthetic failure"):
                self._create()
        self.assertEqual(self._current().revision, before.revision)
        self.assertEqual(self._current().bundle, before.bundle)
        self.assertTrue(self.bridge._unified_store.integrity_check())
        self._create()
        self.assertEqual(self._current().revision, before.revision + 1)

    def test_lan_actor_and_session_cannot_be_chosen_by_client(self):
        service = LanService(self.bridge, self.root / "verified-intake-users.json")
        service.setup_owner("owner", "OwnerPass-2026!")
        owner = service.authenticate("owner", "OwnerPass-2026!")["token"]
        service.upsert_user(owner, {"username": "editor", "role": "editor",
                                    "password": "EditorPass-2026!",
                                    "projects": [PROJECT]})
        editor = service.authenticate("editor", "EditorPass-2026!")["token"]
        command = {"type": "intake.create", "eventId": "lan-create",
                   "intakeId": "lan-intake", "projectId": PROJECT,
                   "cardId": CARD, "stepId": STEP, "quantity": 1,
                   "supplier": deepcopy(VENDOR)}
        baseline = self._current()
        with self.assertRaises(PermissionError):
            service.accounting_command("forged-session", command)
        with self.assertRaises((ValueError, PermissionError)):
            service.accounting_command(owner, {**command, "actor": "owner",
                                               "trusted": True})
        with self.assertRaises(PermissionError):
            service.accounting_command(editor, command)
        self.assertEqual(self._current().revision, baseline.revision)
        response = service.accounting_command(owner, command)
        self.assertEqual(response["bookedPayable"], 0)
        self.assertEqual(self._current().revision, baseline.revision + 1)


if __name__ == "__main__":
    unittest.main()
