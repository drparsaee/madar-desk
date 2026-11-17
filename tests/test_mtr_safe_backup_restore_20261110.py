"""Real three-store SQLite backup/restore; disposable synthetic metadata ONLY.

Every filesystem mutation is confined to TemporaryDirectory owned by
DisposableQAScope. The Taraz registry source is imported read-only; neither
installed software nor genuine profiles, TLS, accounting or network are used.
"""
from __future__ import annotations

from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import qa_mtr_safe_backup_restore_20261110 as qa
from mtr_host_request_store import HostRequestStore, TrustedPrincipal
from mtr_e2_dispatch_gate import OneShotDispatchGate, DispatchGateConflict


def identity():
    return TrustedPrincipal(
        user_id="qa-editor", org_id="qa-org", session_id="qa-session",
        role="editor", project_ids=frozenset({"qa-project"}),
        permissions=frozenset({"mtr.prepare", "mtr.manual_send", "mtr.read"}),
        authenticated=True, session_valid=True,
    )


class SafeThreeDBRecoveryQA(unittest.TestCase):
    def setUp(self):
        self.scope = qa.DisposableQAScope()
        self.addCleanup(self.scope.close)
        self.root = self.scope.root
        self.env = patch.dict(os.environ, {
            "APPDATA": str(self.root / "AppData"), "LOCALAPPDATA": str(self.root / "LocalAppData"),
            "USERPROFILE": str(self.root), "HOME": str(self.root),
            "TEMP": str(self.root), "TMP": str(self.root),
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def stores(self):
        taraz = qa._source_module(qa.TARAZ_REGISTRY_SOURCE)
        outbox = HostRequestStore(self.scope.location("live", "outbox"))
        gate = OneShotDispatchGate(self.scope.location("live", "dispatch"), outbox)
        peer = taraz.TarazPeerRegistry(
            self.scope.location("live", "peer"),
            taraz.PeerConfig("qa-org", "qa-madar", "qa-m-key",
                             "qa-taraz", "qa-t-key", b"m" * 32, b"t" * 32))
        return outbox, gate, peer

    def snapshots(self):
        outbox, gate, peer = self.stores()
        return outbox, gate, peer, qa.make_backups(self.scope, outbox, gate, peer)

    def test_full_synthetic_roundtrip_restores_query_first_and_peer_replay(self):
        result = qa.exercise_synthetic_roundtrip(self.scope)
        self.assertTrue(result["threeBackupsVerified"])
        self.assertTrue(result["threeRestoresNewAndDistinct"])
        self.assertTrue(result["restoredRowsMatchBackup"])
        self.assertTrue(result["restartedUnknownStillQueryFirst"])
        self.assertTrue(result["secondFirstDispatchDenied"])
        self.assertTrue(result["peerRequestIdempotentAfterRestart"])
        self.assertTrue(result["peerQueryBindingSurvivesRestart"])
        self.assertFalse(result["officialFinanceReceiptVerified"])
        self.assertFalse(result["realTlsTransportAuthenticated"])
        self.assertFalse(result["restoredDispatchEnabled"])
        self.assertFalse(result["threeDatabaseAtomicEpochVerified"])
        self.assertFalse(result["realServiceRestartOrPowerLossVerified"])
        self.assertFalse(result["peerRuntimeSecretsBackedUp"])
        for kind in qa.NAMES:
            source = self.scope.location("backups", kind)
            copied = self.scope.location("restored", kind)
            self.assertTrue(source.exists() and copied.exists())
            self.assertNotEqual(source, copied)
            self.assertEqual(qa._sqlite_readback(copied, kind)["integrity"], "ok")
        self.assertFalse((self.root / "finance.sqlite3").exists())

    def test_backup_three_stores_hash_integrity_and_read_only_sqlite(self):
        _, _, _, evidence = self.snapshots()
        self.assertEqual(evidence["kinds"], list(qa.NAMES))
        self.assertEqual(set(evidence["snapshots"]), set(qa.NAMES))
        for kind in qa.NAMES:
            backup = evidence["snapshots"][kind]
            self.assertEqual(backup["sha256"], qa._sha(self.scope.location("backups", kind)))
            self.assertEqual(backup["integrity"], "ok")
            self.assertEqual(backup["userVersion"], 1)
            self.assertTrue(backup["queryOnly"])
        control = evidence["snapshots"]["dispatch"]["tables"]["dispatch_control"]
        self.assertEqual(control["rows"], 1)
        with closing(sqlite3.connect(self.scope.location("backups", "dispatch"))) as db:
            self.assertEqual(db.execute(
                "SELECT first_permits_enabled FROM dispatch_control").fetchone(), (0,))
        self.assertEqual(qa.validate_backups(self.scope), evidence)
        self.assertFalse(evidence["restoreActivationAllowed"])

    def test_restores_are_new_distinct_files_preserving_full_row_digests(self):
        _, _, _, original = self.snapshots()
        restored = qa.restore_backups(self.scope)
        self.assertEqual(restored["restoredCount"], 3)
        self.assertFalse(restored["reEnabledFirstDispatch"])
        for kind in qa.NAMES:
            self.assertEqual(restored["restored"][kind]["tables"],
                             original["snapshots"][kind]["tables"])
            self.assertEqual(restored["restored"][kind]["userVersion"], 1)
            self.assertEqual(self.scope.location("restored", kind).stat().st_nlink, 1)

    def test_live_change_after_snapshot_does_not_change_backup_readback(self):
        outbox, gate, peer, baseline = self.snapshots()
        principal = identity()
        rid = "d" * 32
        payload = {"schema": 1, "source": "madar", "id": rid,
                   "taskId": "after-backup-only", "projectId": "qa-project",
                   "title": "Synthetic live mutation", "createdUtc": "2026-11-10T12:00:00+00:00"}
        outbox.prepare_request(
            principal=principal, request_id=rid, payload=payload,
            base_revision=4, current_server_revision=4,
            prepare_key="only-post-backup-0001", explicit_manual_action=True)
        self.assertEqual(qa.validate_backups(self.scope), baseline)
        restored = qa.restore_backups(self.scope)
        self.assertEqual(restored["restored"]["outbox"]["tables"],
                         baseline["snapshots"]["outbox"]["tables"])
        recovered = HostRequestStore(self.scope.location("restored", "outbox"))
        with self.assertRaises(KeyError):
            recovered.receipt_status(principal=principal, request_id=rid,
                                     expected_base_revision=4)

    def test_reopening_restored_gate_disallows_new_reservation(self):
        self.snapshots()
        qa.restore_backups(self.scope)
        restored_outbox = HostRequestStore(self.scope.location("restored", "outbox"))
        restored_gate = OneShotDispatchGate(self.scope.location("restored", "dispatch"),
                                             restored_outbox)
        principal = identity()
        rid = "f" * 32
        payload = {"schema": 1, "source": "madar", "id": rid,
                   "taskId": "qa-task", "projectId": "qa-project",
                   "title": "Synthetic forbidden dispatch",
                   "createdUtc": "2026-11-10T12:00:00+00:00"}
        prepared = restored_outbox.prepare_request(
            principal=principal, request_id=rid, payload=payload,
            base_revision=7, current_server_revision=7,
            prepare_key="restore-prep-only-0001", explicit_manual_action=True)
        restored_outbox.manual_send(
            principal=principal, request_id=rid,
            expected_payload_sha256=prepared["payloadSha256"],
            expected_base_revision=7, current_server_revision=7,
            send_key="restore-send-only-0001", explicit_manual_action=True)
        with self.assertRaises(PermissionError):
            restored_gate.reserve_once(
                principal=principal, request_id=rid,
                expected_payload_sha256=prepared["payloadSha256"],
                expected_base_revision=7, current_server_revision=7,
                send_key="restore-send-only-0001")
        self.assertEqual(restored_gate.path, self.scope.location("restored", "dispatch"))

    def test_duplicate_backup_destinations_are_refused_without_overwrite(self):
        outbox, gate, peer, original = self.snapshots()
        sha_before = {kind: qa._sha(self.scope.location("backups", kind))
                      for kind in qa.NAMES}
        with self.assertRaises(FileExistsError):
            qa.make_backups(self.scope, outbox, gate, peer)
        self.assertEqual({kind: qa._sha(self.scope.location("backups", kind))
                          for kind in qa.NAMES}, sha_before)
        self.assertEqual(original, qa.validate_backups(self.scope))

    def test_duplicate_restore_target_refuses_before_other_writes(self):
        self.snapshots()
        existing = self.scope.location("restored", "peer")
        existing.write_bytes(b"preexisting-disposable-marker")
        with self.assertRaises(FileExistsError):
            qa.restore_backups(self.scope)
        self.assertEqual(existing.read_bytes(), b"preexisting-disposable-marker")
        for kind in ("outbox", "dispatch"):
            self.assertFalse(self.scope.location("restored", kind).exists())

    def test_missing_backup_and_extra_file_both_fail_closed(self):
        self.snapshots()
        path = self.scope.location("backups", "peer")
        path.unlink()
        with self.assertRaises(qa.QABackupDenied):
            qa.restore_backups(self.scope)
        self.assertFalse(any(self.scope.location("restored", kind).exists()
                             for kind in qa.NAMES))
        self.scope.location("backups", "peer").write_bytes(b"not a database")
        (self.scope.root / "backups" / "duplicate.sqlite3").write_bytes(b"fake")
        with self.assertRaisesRegex(qa.QABackupDenied, "backup_missing_extra"):
            qa.validate_backups(self.scope)

    def test_corrupted_backup_payload_fails_before_any_restore(self):
        self.snapshots()
        file = self.scope.location("backups", "outbox")
        content = bytearray(file.read_bytes())
        content[0:16] = b"not-sqlite-header"
        file.write_bytes(content)
        with self.assertRaises((qa.QABackupDenied, sqlite3.DatabaseError)):
            qa.restore_backups(self.scope)
        self.assertFalse(any(self.scope.location("restored", kind).exists()
                             for kind in qa.NAMES))

    def test_snapshot_sha_mismatch_even_if_valid_sqlite_is_refused(self):
        self.snapshots()
        file = self.scope.location("backups", "outbox")
        # This is a valid SQLite mutation, with no broken foreign key, to
        # prove a *digest* mismatch is still independently detected.
        changed = HostRequestStore(file)
        rid = "f" * 32
        changed.prepare_request(
            principal=identity(), request_id=rid,
            payload={"schema": 1, "source": "madar", "id": rid,
                     "taskId": "synthetic-tamper", "projectId": "qa-project",
                     "title": "Synthetic backup tampering",
                     "createdUtc": "2026-11-10T12:00:00+00:00"},
            base_revision=3, current_server_revision=3,
            prepare_key="synthetic-tamper-0001", explicit_manual_action=True)
        self.assertEqual(qa._sqlite_readback(file, "outbox")["integrity"], "ok")
        with self.assertRaisesRegex(qa.QABackupDenied, "backup_sha_integrity_or_content_mismatch"):
            qa.validate_backups(self.scope)

    def test_missing_and_duplicate_manifest_keys_are_blocked(self):
        self.snapshots()
        file = self.scope.manifest()
        original = file.read_text(encoding="utf-8")
        data = json.loads(original)
        del data["snapshots"]["peer"]
        file.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(qa.QABackupDenied):
            qa.restore_backups(self.scope)
        file.write_text(original.replace('"schema":1', '"schema":1,"schema":1', 1),
                        encoding="utf-8")
        with self.assertRaises(qa.QABackupDenied):
            qa.restore_backups(self.scope)
        self.assertFalse(any(self.scope.location("restored", kind).exists()
                             for kind in qa.NAMES))

    def test_no_missing_required_source_capabilities_silently_substituted(self):
        outbox, gate, peer = self.stores()
        for target, capability in ((outbox, "backup_to"), (gate, "backup_to"),
                                    (peer, "archive_to")):
            with self.subTest(capability=capability):
                with patch.object(target, capability, None):
                    with self.assertRaisesRegex(
                            qa.QABackupDenied, "required_create_only_backup_api_missing"):
                        qa.make_backups(self.scope, outbox, gate, peer)
                self.assertFalse(self.scope.manifest().exists())

    def test_duplicate_source_database_path_or_source_outside_scope_denied(self):
        outbox, gate, peer = self.stores()
        other = self.root / "alternate.sqlite3"
        outside_scope_but_disposable = HostRequestStore(other)
        with self.assertRaisesRegex(qa.QABackupDenied,
                                    "source_database_outside_disposable_scope"):
            qa.make_backups(self.scope, outside_scope_but_disposable, gate, peer)
        self.assertFalse(self.scope.manifest().exists())

    def test_linked_backup_or_restore_path_is_denied(self):
        self.snapshots()
        target = self.scope.location("backups", "peer")
        outside = self.root / "synthetic-nonbackup.sqlite3"
        outside.write_bytes(target.read_bytes())
        target.unlink()
        try:
            target.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("Windows symlink privilege is not available")
        with self.assertRaisesRegex(qa.QABackupDenied, "linked_or_junction_path"):
            qa.restore_backups(self.scope)
        self.assertFalse(any(self.scope.location("restored", kind).exists()
                             for kind in qa.NAMES))

    def test_scope_close_blocks_backup_restoration(self):
        self.snapshots()
        self.scope.close()
        with self.assertRaisesRegex(qa.QABackupDenied,
                                    "closed_or_non_disposable_scope"):
            qa.restore_backups(self.scope)

    def test_peer_module_missing_capability_refuses_without_fallback(self):
        wrong = self.root / "not-found.py"
        with self.assertRaises(qa.QABackupDenied):
            qa._source_module(wrong)
        self.assertFalse(any(self.scope.location("backups", kind).exists()
                             for kind in qa.NAMES))

    def test_main_cli_returns_only_synthetic_and_never_operational_authority(self):
        tool = qa.ROOT / "scripts" / "qa_mtr_safe_backup_restore_20261110.py"
        proc = subprocess.run([sys.executable, "-B", str(tool)],
                              capture_output=True, text=True, timeout=35)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        obj = json.loads(proc.stdout.strip())
        self.assertTrue(obj["syntheticOnly"])
        self.assertTrue(obj["threeBackupsVerified"])
        self.assertTrue(obj["secondFirstDispatchDenied"])
        self.assertFalse(obj["officialFinanceReceiptVerified"])
        self.assertFalse(obj["restoredDispatchEnabled"])
        self.assertFalse(obj["threeDatabaseAtomicEpochVerified"])


if __name__ == "__main__":
    unittest.main()
