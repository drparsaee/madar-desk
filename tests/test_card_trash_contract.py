"""CD05 P0: task.deleted host, Bridge persistence, LAN ACL/CAS acceptance.

Expected to fail until Prime wires Python strict bool validation and UI path.
NO real APPDATA, LAN socket, Git, release or destructive user data operations.
The two backend instances use a unique disposable temporary root *per test*.
"""

import base64
from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app_storage import UnifiedAppStorage
from data_model import normalize_plus, validate_plus
from lan import LanService
import native_app

CARD_ID = "example-2"
OTHER_CARD = "example-3"
PROJECT_ID = "p-sample"
PRICE = 8_630_007
CARD_COST = 1_805_011
STEP_COST = 75_091
ATTACHMENT = base64.b64encode(b"CD05 verified attachment bytes\n").decode("ascii")


def card(state, ident=CARD_ID):
    return next(c for c in state["tasks"] if c["id"] == ident)


def project(state):
    return next(p for p in state["projects"] if p["id"] == PROJECT_ID)


def sale():
    return {"customer": {"name": "CD05 client", "reference": ""},
            "lines": [{"id": "line-one", "description": "Proof print",
                       "quantity": 1, "unitPrice": 491_000}],
            "discount": 0, "tax": 0, "advance": 0, "autoInvoice": True}


class TrashModelContractTests(unittest.TestCase):
    def test_legacy_missing_deleted_is_accepted_and_normalized_losslessly(self):
        source = native_app.initial_state()
        before = deepcopy(source)
        self.assertTrue(all("deleted" not in t for t in source["tasks"]))
        normalized = native_app.normalize_state(source)
        self.assertTrue(validate_plus(normalized))
        self.assertTrue(native_app.is_valid(normalized))
        self.assertEqual(source, before, "Normalization mutated the input")
        self.assertEqual(native_app.normalize_state(normalized), normalized)
        self.assertNotIn("deleted", card(normalized))

    def test_only_strict_boolean_deleted_is_accepted_on_both_validators(self):
        original = native_app.normalize_state(native_app.initial_state())
        for flag in (True, False):
            state = deepcopy(original)
            card(state)["deleted"] = flag
            self.assertTrue(validate_plus(state))
            self.assertTrue(native_app.is_valid(state))
            self.assertEqual(native_app.normalize_state(state), state)
        for flag in (None, 0, 1, "", "true", "false", [], {}, 1.5):
            for validator in (validate_plus, native_app.is_valid):
                with self.subTest(value=repr(flag), validator=validator.__name__):
                    candidate = deepcopy(original)
                    card(candidate)["deleted"] = flag
                    unchanged = deepcopy(candidate)
                    with self.assertRaisesRegex(ValueError, "deleted|حذف|زباله"):
                        validator(candidate)
                    self.assertEqual(candidate, unchanged)


class TrashIsolatedFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="madar-cd05-trash-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.assertTrue(self.root.is_dir())
        environment = patch.dict(os.environ, {
            "APPDATA": str(self.root), "LOCALAPPDATA": str(self.root)
        })
        environment.start()
        self.addCleanup(environment.stop)
        fake_datadir = patch.object(native_app, "datadir", return_value=self.root)
        fake_datadir.start()
        self.addCleanup(fake_datadir.stop)
        self.bridge = native_app.Bridge()
        self._check_root(self.bridge)
        self.assertEqual(self.bridge.connection.get("mode"), "solo")

    def _check_root(self, instance):
        for path in (instance.path, instance.unified_path, instance.unified_marker,
                     instance.finance_path, instance.collab_path,
                     instance.finance_outbox_path, instance.automation_outbox_path):
            self.assertEqual(path.resolve().parent, self.root)
        self.assertEqual(instance.backups_dir.resolve().parent, self.root)

    def _configure(self, *, sqlite=False):
        if sqlite:
            self.assertEqual(self.bridge.enableUnifiedStorage()["mode"], "sqlite")
        # Contract plus a real invoice: complete a card after contract.set.
        self.bridge.financeCommand({
            "type": "contract.set", "eventId": "cd05-contract",
            "cardId": CARD_ID, "sale": sale(),
        })
        state = self.bridge.getStateForUi()
        project(state).update(price=PRICE, costEnabled=True)
        task = card(state)
        task.update({
            "cardOrder": 410, "cost": CARD_COST, "costEnabled": True,
            "costCategory": "print", "costDate": "2026-10-21",
            "fileLinks": [{"id": "share-1", "name": "proof.pdf",
                           "path": "\\\\server\\share\\proof.pdf"}],
            "status": "done", "listId": "done",
            "archived": False,
        })
        task["checklist"][0].update({
            "cost": STEP_COST, "costCategory": "cut", "costDate": "2026-10-21"
        })
        self.bridge.saveState(state)
        invoices = self.bridge.financeRead(PROJECT_ID)
        self.assertEqual(len(invoices), 1)
        self.assertEqual(invoices[0]["status"], "Draft")
        uploaded = self.bridge.attachmentUpload(
            CARD_ID, "evidence.txt", ATTACHMENT, "cd05-attachment-upload"
        )
        self.assertEqual(self.bridge.attachmentRead(uploaded["id"])["contentBase64"],
                         ATTACHMENT)
        self.assertEqual(len(self.bridge.attachmentList(CARD_ID)), 1)
        self.assertEqual(len(self.bridge._load_finance()["invoices"]), 1)
        return uploaded

    def _snapshots(self):
        state = self.bridge.getState()
        return {
            "tasks": deepcopy(state["tasks"]),
            "projects": deepcopy(state["projects"]),
            "finance": deepcopy(self.bridge._load_finance()),
            "attachment_records": deepcopy(self.bridge.attachmentList(CARD_ID)),
            "attachment_bytes": self.bridge.attachmentRead(
                self.bridge.attachmentList(CARD_ID)[0]["id"])["contentBase64"],
        }

    def _assert_retained(self, current, baseline, *, deleted):
        self.assertEqual(len(current["tasks"]), len(baseline["tasks"]))
        old = next(t for t in baseline["tasks"] if t["id"] == CARD_ID)
        updated = card(current)
        self.assertIs(updated["deleted"], deleted)
        self.assertEqual({k: v for k, v in updated.items() if k != "deleted"}, old)
        self.assertEqual([t for t in current["tasks"] if t["id"] != CARD_ID],
                         [t for t in baseline["tasks"] if t["id"] != CARD_ID])
        self.assertEqual(current["projects"], baseline["projects"])
        self.assertEqual(self.bridge._load_finance(), baseline["finance"])
        self.assertEqual(self.bridge.attachmentList(CARD_ID),
                         baseline["attachment_records"])
        self.assertEqual(self.bridge.attachmentRead(
            baseline["attachment_records"][0]["id"])["contentBase64"],
            baseline["attachment_bytes"])
        self.assertEqual(updated["cardOrder"], 410)
        self.assertEqual(updated["status"], "done")
        self.assertEqual(updated["listId"], "done")
        self.assertEqual(updated["cost"], CARD_COST)
        self.assertEqual(updated["checklist"][0]["cost"], STEP_COST)
        self.assertEqual(project(current)["price"], PRICE)
        self.assertEqual(len(self.bridge._load_finance()["invoices"]), 1)


class TrashBridgeContractTests(TrashIsolatedFixture):
    def _roundtrip(self, *, sqlite):
        self._configure(sqlite=sqlite)
        baseline = self._snapshots()
        ui = self.bridge.getStateForUi()
        card(ui)["deleted"] = True
        first = self.bridge.saveState(ui)
        self.assertIn("localRevision", first)
        new = native_app.Bridge()
        self._check_root(new)
        old_bridge = self.bridge
        self.bridge = new
        self._assert_retained(new.getState(), baseline, deleted=True)
        self.assertTrue(native_app.is_valid(new.getState()))
        if sqlite:
            store = UnifiedAppStorage(new.unified_path)
            self.assertTrue(store.integrity_check())
            self.assertTrue(next(t for t in store.load().bundle["tasks"]["tasks"]
                                 if t["id"] == CARD_ID)["deleted"])
        else:
            self.assertIn(b'"deleted": true', new.path.read_bytes())
        undo = new.getStateForUi()
        card(undo)["deleted"] = False
        new.saveState(undo)
        reopened = native_app.Bridge()
        self._check_root(reopened)
        self.bridge = reopened
        self._assert_retained(reopened.getState(), baseline, deleted=False)
        self.assertTrue(native_app.is_valid(reopened.getState()))
        self.bridge = old_bridge

    def test_json_soft_delete_and_restore_reopen_all_finance_attachment_refs(self):
        self._roundtrip(sqlite=False)

    def test_sqlite_soft_delete_and_restore_reopen_all_finance_attachment_refs(self):
        self._roundtrip(sqlite=True)

    def _invalid_write(self, *, sqlite):
        self._configure(sqlite=sqlite)
        before = self._snapshots()
        before_state = deepcopy(self.bridge.getState())
        before_storage = (UnifiedAppStorage(self.bridge.unified_path).load().revision
                          if sqlite else self.bridge.path.read_bytes())
        invalid = self.bridge.getStateForUi()
        card(invalid)["deleted"] = "true"
        with self.assertRaises(ValueError):
            self.bridge.saveState(invalid)
        after_storage = (UnifiedAppStorage(self.bridge.unified_path).load().revision
                         if sqlite else self.bridge.path.read_bytes())
        self.assertEqual(after_storage, before_storage)
        self.assertEqual(self.bridge.getState(), before_state)
        self.assertEqual(self._snapshots(), before)

    def test_json_invalid_deleted_refuses_save_without_mutating_finance(self):
        self._invalid_write(sqlite=False)

    def test_sqlite_invalid_deleted_refuses_save_without_mutating_finance(self):
        self._invalid_write(sqlite=True)


class TrashLanContractTests(TrashIsolatedFixture):
    def setUp(self):
        super().setUp()
        self._configure()
        self.host = LanService(self.bridge, self.root / "users.json",
                               bind="127.0.0.1", port=0)
        self.host.setup_owner("admin", "cd05-strong-admin-password")
        self.admin = self.host.authenticate(
            "admin", "cd05-strong-admin-password")["token"]
        for name, role, scope in (
            ("editor", "editor", [PROJECT_ID]),
            ("viewer", "viewer", [PROJECT_ID]),
            ("foreign", "editor", ["p-personal"]),
        ):
            self.host.upsert_user(self.admin, {
                "username": name, "role": role, "projects": scope,
                "password": f"cd05-{name}-strong-password",
            })
        self.editor = self.host.authenticate(
            "editor", "cd05-editor-strong-password")["token"]
        self.viewer = self.host.authenticate(
            "viewer", "cd05-viewer-strong-password")["token"]
        self.foreign = self.host.authenticate(
            "foreign", "cd05-foreign-strong-password")["token"]

    def test_editor_soft_delete_and_restore_card_only_with_project_grant(self):
        baseline = self._snapshots()
        view = self.host.read_state(self.editor)
        self.assertEqual({t["projectId"] for t in view["state"]["tasks"]},
                         {PROJECT_ID})
        self.assertEqual(project(view["state"])["price"], 0)
        candidate = deepcopy(view["state"])
        card(candidate)["deleted"] = True
        changed = self.host.write_state(self.editor, candidate, view["revision"])
        self.assertNotEqual(changed["revision"], view["revision"])
        self._assert_retained(self.bridge.getState(), baseline, deleted=True)
        newest = deepcopy(self.host.read_state(self.editor))
        card(newest["state"])["deleted"] = False
        self.host.write_state(
            self.editor, newest["state"], newest["revision"])
        self._assert_retained(self.bridge.getState(), baseline, deleted=False)

    def test_admin_can_soft_delete_and_restore_without_purging_finance(self):
        baseline = self._snapshots()
        first = self.host.read_state(self.admin)
        changed = deepcopy(first["state"])
        card(changed)["deleted"] = True
        reply = self.host.write_state(self.admin, changed, first["revision"])
        self.assertNotEqual(reply["revision"], first["revision"])
        self._assert_retained(self.bridge.getState(), baseline, deleted=True)
        card(reply["state"])["deleted"] = False
        self.host.write_state(self.admin, reply["state"], reply["revision"])
        self._assert_retained(self.bridge.getState(), baseline, deleted=False)

    def test_viewer_and_foreign_editor_cannot_mutate_out_of_scope_card(self):
        before_state = deepcopy(self.bridge.getState())
        before = self._snapshots()
        view = self.host.read_state(self.viewer)
        forged = deepcopy(view["state"])
        card(forged)["deleted"] = True
        with self.assertRaises(PermissionError):
            self.host.write_state(self.viewer, forged, view["revision"])
        external = self.host.read_state(self.foreign)
        forged_other = deepcopy(external["state"])
        inserted = deepcopy(card(before_state))
        inserted["deleted"] = True
        forged_other["tasks"].append(inserted)
        with self.assertRaises((PermissionError, ValueError)):
            self.host.write_state(
                self.foreign, forged_other, external["revision"])
        self.assertEqual(self.bridge.getState(), before_state)
        self.assertEqual(self._snapshots(), before)

    def test_stale_admin_and_editor_cas_cannot_undo_first_trash_write(self):
        first = self.host.read_state(self.admin)
        stale_admin = deepcopy(first["state"])
        card(stale_admin)["deleted"] = True
        outcome = self.host.write_state(
            self.admin, stale_admin, first["revision"])
        self.assertTrue(card(outcome["state"])["deleted"])
        with self.assertRaisesRegex(RuntimeError, "CONFLICT"):
            self.host.write_state(
                self.admin, first["state"], first["revision"])
        old_editor = self.host.read_state(self.editor)
        new_admin = self.host.read_state(self.admin)
        restored = deepcopy(new_admin["state"])
        card(restored)["deleted"] = False
        self.host.write_state(
            self.admin, restored, new_admin["revision"])
        with self.assertRaisesRegex(RuntimeError, "CONFLICT"):
            self.host.write_state(
                self.editor, old_editor["state"], old_editor["revision"])
        self.assertIs(card(self.bridge.getState())["deleted"], False)
        self.assertEqual(len(self.bridge._load_finance()["invoices"]), 1)


if __name__ == "__main__":
    unittest.main()
