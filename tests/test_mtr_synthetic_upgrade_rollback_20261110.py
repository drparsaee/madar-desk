"""Fail-closed real SQLite disposable upgrade/rollback tests, never installers.

The main source helper is imported READ-ONLY. Artifacts are read/hashed but
never executed. Tests may mutate ONLY their own TemporaryDirectory scope.
"""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import qa_mtr_safe_backup_restore_20261110 as base
from scripts import qa_mtr_synthetic_upgrade_rollback_20261110 as qa


class SyntheticUpgradeRollbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # This is the same SHA pin authority the CLI checks; it does not
        # claim source authenticity or production release eligibility.
        cls.pins = qa.verify_both_artifact_pins()

    def setUp(self):
        self.scope = base.DisposableQAScope()
        self.addCleanup(self.scope.close)
        self.root = self.scope.root
        self.env = patch.dict(os.environ, {
            "APPDATA": str(self.root / "synthetic-appdata"),
            "LOCALAPPDATA": str(self.root / "synthetic-localappdata"),
            "USERPROFILE": str(self.root),
            "HOME": str(self.root),
            "TEMP": str(self.root),
            "TMP": str(self.root),
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def prepare_checkpoint(self):
        state = qa._first_state(self.scope)
        manifest = base.make_backups(
            self.scope, state["outbox"], state["gate"], state["peer"])
        digest = base._sha(self.scope.manifest())
        reference = qa._checkpoint_observations(self.scope, manifest)
        plan = qa.make_upgrade_plan(self.pins, digest)
        qa.validate_upgrade_plan(plan, self.pins, digest)
        return state, manifest, digest, reference, plan

    def prepare_upgraded(self):
        state, manifest, digest, reference, plan = self.prepare_checkpoint()
        upgraded = qa._synthetic_upgrade(
            self.scope, state, plan, self.pins, digest)
        return state, manifest, digest, reference, plan, upgraded

    def test_real_both_source_artifacts_are_pinned_qa_only_no_installer(self):
        pins = self.pins
        self.assertEqual(pins["versions"], {
            "madar": "1.0.23", "taraz": "1.0.0"})
        self.assertEqual(pins["artifactSha256"], qa.EXE_SHA)
        self.assertEqual(pins["sourceSnapshotSha256"], qa.SNAPSHOT_SHA)
        self.assertEqual(pins["madarSourceFileCount"], 6501)
        self.assertEqual(pins["tarazReportedSourceFileCount"], 120)
        self.assertTrue(pins["qaOnly"])
        self.assertFalse(pins["installerOrProductionReleaseVerified"])

    def test_real_synthetic_upgrade_then_new_rollback_exact_bytes_and_replay_denial(self):
        state, manifest, digest, reference, plan, upgraded = self.prepare_upgraded()
        self.assertEqual(
            set(reference), set(base.NAMES))
        for kind in base.NAMES:
            self.assertNotEqual(upgraded[kind]["sha256"],
                                reference[kind]["sha256"])
        restored = qa.rollback_new_destinations(self.scope, manifest, reference)
        self.assertEqual(len(restored), 3)
        for kind in base.NAMES:
            target = self.root / qa.ROLLBACK_FOLDER / (kind + ".sqlite3")
            source = self.scope.location("backups", kind)
            self.assertTrue(target.is_file())
            self.assertNotEqual(target, source)
            self.assertNotEqual(target, self.scope.location("live", kind))
            self.assertEqual(restored[kind]["sha256"], reference[kind]["sha256"])
            self.assertEqual(base._sha(target), base._sha(source))
            self.assertTrue(restored[kind]["rowDigestMatches"])
            self.assertEqual(target.stat().st_nlink, 1)
        safety = qa._verify_no_replay(self.scope, state, upgraded)
        self.assertTrue(safety["previouslyConsumedHostSlotDenied"])
        self.assertTrue(safety["newFirstDispatchDeniedAfterRollback"])
        self.assertTrue(safety["peerQueryReplayBindingRetained"])
        self.assertTrue(safety["upgradeOnlyRequestNotRestored"])
        self.assertFalse(safety["financialReceiptVerified"])
        for kind in base.NAMES:
            self.assertEqual(base._sha(
                self.root / qa.ROLLBACK_FOLDER / (kind + ".sqlite3")),
                reference[kind]["sha256"])
            self.assertNotEqual(base._sha(self.scope.location("live", kind)),
                                reference[kind]["sha256"])

    def test_restarting_qa_twice_never_reuses_source_or_destination_path(self):
        # Two separate disposable scopes, neither writes to installed apps.
        result = qa.run()
        self.assertEqual(result["status"], "SYNTHETIC_ROLLBACK_PASS_NOT_RELEASE")
        self.assertEqual(result["releaseDecision"], "NO_GO")
        self.assertEqual(result["signingPolicy"], "UNSIGNED_QA_ONLY")
        self.assertTrue(result["exactOriginalSnapshotDigestRestored"])
        self.assertEqual(result["restoredStoreCount"], 3)
        self.assertTrue(result["priorDispatchReplayDenied"])
        self.assertTrue(result["freshDispatchAfterRollbackDenied"])
        self.assertFalse(result["threeDatabaseAtomicEpochVerified"])
        self.assertFalse(result["realInstallerExecuted"])
        self.assertFalse(result["realProfilesOrInstalledAppsTouched"])
        self.assertFalse(result["mayInstall"])
        self.assertFalse(result["realCrossAppActorBindingVerified"])

    def test_unknown_source_qa_sha_pin_rejects_forged_artifact(self):
        with tempfile.TemporaryDirectory(prefix="mtr-qa-forged-report-") as folder:
            forged = Path(folder) / "forged-qa-report.json"
            forged.write_text('{"status":"QA_BUNDLE_VERIFIED","source":"malicious"}',
                              encoding="utf-8")
            with self.assertRaisesRegex(qa.RollbackDenied, "pin_mismatch"):
                qa._read_json(forged, qa.REPORT_SHA["taraz"])
            with self.assertRaisesRegex(
                    qa.RollbackDenied, "unknown_or_missing_source_sha256_pin"):
                qa._safe_read(forged, "", max_size=1000)

    def test_taraz_unknown_source_path_missing_is_not_accepted_as_build(self):
        fake = self.root / "synthetic-untrusted-peer-source.py"
        with patch.object(base, "TARAZ_REGISTRY_SOURCE", fake):
            with self.assertRaises(qa.RollbackDenied):
                qa.verify_both_artifact_pins()

    def test_missing_executable_or_report_cannot_mint_source_attestation(self):
        nonexistent = self.root / "no-qa-exe.exe"
        with patch.object(qa, "TARAZ_EXE", nonexistent):
            with self.assertRaises(qa.RollbackDenied):
                qa.verify_both_artifact_pins()
        with patch.object(qa, "MADAR_BUNDLE", self.root / "not-a-bundle"):
            with self.assertRaises(qa.RollbackDenied):
                qa.verify_both_artifact_pins()

    def test_unknown_madar_or_taraz_app_version_not_trusted(self):
        m = qa._read_json(qa.MADAR_BUNDLE / "qa-build-result.json",
                          qa.REPORT_SHA["madar"])
        p = qa._read_json(qa.MADAR_BUNDLE / "qa-provenance.json",
                          qa.REPORT_SHA["madar_provenance"])
        i = qa._read_json(qa.MADAR_BUNDLE / "source-input-sha256.json",
                          qa.REPORT_SHA["madar_source_inventory"])
        t = qa._read_json(qa.TARAZ_BUNDLE / "qa-build-report.json",
                          qa.REPORT_SHA["taraz"])
        mp = qa._read_json(qa.MADAR_BUNDLE / "source" / "package.json",
                           qa.PACKAGE_SHA["madar"])
        tp = qa._read_json(qa.TARAZ_BUNDLE / "snapshot" / "package.json",
                           qa.PACKAGE_SHA["taraz"])
        valid = qa._validate_artifact_reports(m, p, i, t, mp, tp)
        self.assertTrue(valid["qaOnly"])
        for mutated_pkg, version in (({**mp, "version": "1.0.27"}, "Madar"),
                                     ({**tp, "version": "unknown"}, "Taraz")):
            with self.subTest(app=version):
                args = (mutated_pkg, tp) if version == "Madar" else (mp, mutated_pkg)
                with self.assertRaisesRegex(
                        qa.RollbackDenied, "unknown_or_mismatched_source_application_version"):
                    qa._validate_artifact_reports(m, p, i, t, *args)

    def test_qa_only_release_flag_or_snapshot_pin_forgery_rejected(self):
        m = qa._read_json(qa.MADAR_BUNDLE / "qa-build-result.json",
                          qa.REPORT_SHA["madar"])
        p = qa._read_json(qa.MADAR_BUNDLE / "qa-provenance.json",
                          qa.REPORT_SHA["madar_provenance"])
        i = qa._read_json(qa.MADAR_BUNDLE / "source-input-sha256.json",
                          qa.REPORT_SHA["madar_source_inventory"])
        t = qa._read_json(qa.TARAZ_BUNDLE / "qa-build-report.json",
                          qa.REPORT_SHA["taraz"])
        mp = qa._read_json(qa.MADAR_BUNDLE / "source" / "package.json",
                           qa.PACKAGE_SHA["madar"])
        tp = qa._read_json(qa.TARAZ_BUNDLE / "snapshot" / "package.json",
                           qa.PACKAGE_SHA["taraz"])
        badm = deepcopy(m)
        badm["application"]["releaseReady"] = True
        with self.assertRaisesRegex(
                qa.RollbackDenied, "unknown_or_incomplete_madar"):
            qa._validate_artifact_reports(badm, p, i, t, mp, tp)
        badt = deepcopy(t)
        badt["sourceSnapshotSha256"] = "f" * 64
        with self.assertRaisesRegex(
                qa.RollbackDenied, "unknown_or_incomplete_taraz"):
            qa._validate_artifact_reports(m, p, i, badt, mp, tp)

    def test_upgrade_plan_unknown_source_version_invalid_actions_and_flags(self):
        state, manifest, digest, reference, plan = self.prepare_checkpoint()
        for change in (
            {"sourceAppVersions": {"madar": "1.0.27", "taraz": "1.0.0"}},
            {"sourceAppVersions": {"madar": "1.0.23", "taraz": "9000.0.0"}},
            {"sourceArtifactSha256": {"madar": "0" * 64,
                                      "taraz": qa.EXE_SHA["taraz"]}},
            {"sourceSnapshotSha256": {"madar": qa.SNAPSHOT_SHA["madar"],
                                      "taraz": "0" * 64}},
            {"mutations": ["run-real-installer"]},
            {"officialFinancePosting": True},
            {"actualInstallerOrMigrationRun": True},
            {"crossStoreAtomicityVerified": True},
            {"checkpointManifestSha256": "0" * 64},
            {"toMetadataEpoch": 3},
            {"untrustedKey": "extra"},
        ):
            with self.subTest(change=change), self.assertRaisesRegex(
                    qa.RollbackDenied, "untrusted_upgrade_plan"):
                qa.validate_upgrade_plan({**plan, **change}, self.pins, digest)
        self.assertFalse((self.root / qa.UPGRADE_FOLDER).exists())
        self.assertFalse((self.root / qa.ROLLBACK_FOLDER).exists())

    def test_synthetic_plan_file_sha_and_exact_semantics_checked_before_upgrade(self):
        _, _, digest, _, plan = self.prepare_checkpoint()
        path = qa._plan_file(self.scope, plan)
        original = base._sha(path)
        verified = qa.verify_disposable_upgrade_plan_file(
            self.scope, original, self.pins, digest)
        self.assertEqual(verified, plan)
        self.assertFalse((self.root / qa.ROLLBACK_FOLDER).exists())
        path.write_bytes(path.read_bytes() + b"tamper")
        with self.assertRaisesRegex(
                qa.RollbackDenied, "synthetic_upgrade_plan_changed_or_unknown"):
            qa.verify_disposable_upgrade_plan_file(
                self.scope, original, self.pins, digest)
        self.assertFalse((self.root / qa.ROLLBACK_FOLDER).exists())

    def test_duplicate_json_plan_keys_block_even_under_recomputed_test_hash(self):
        _, _, digest, _, plan = self.prepare_checkpoint()
        path = qa._plan_file(self.scope, plan)
        modified = path.read_bytes().replace(
            b'"schema":1', b'"schema":1,"schema":1', 1)
        path.write_bytes(modified)
        tampered_hash = base._sha(path)
        with self.assertRaises(base.QABackupDenied):
            qa.verify_disposable_upgrade_plan_file(
                self.scope, tampered_hash, self.pins, digest)
        self.assertFalse((self.root / qa.ROLLBACK_FOLDER).exists())

    def test_missing_snapshot_refused_before_creating_rollback_folder(self):
        _, checkpoint, _, reference, _, _ = self.prepare_upgraded()
        self.scope.location("backups", "peer").unlink()
        with self.assertRaises(base.QABackupDenied):
            qa.rollback_new_destinations(self.scope, checkpoint, reference)
        self.assertFalse((self.root / qa.ROLLBACK_FOLDER).exists())

    def test_corrupt_snapshot_refused_before_any_rollback_output(self):
        _, checkpoint, _, reference, _, _ = self.prepare_upgraded()
        target = self.scope.location("backups", "outbox")
        payload = bytearray(target.read_bytes())
        payload[:16] = b"invalid-sqlite-db"
        target.write_bytes(payload)
        with self.assertRaises((base.QABackupDenied, qa.RollbackDenied,
                                sqlite3.DatabaseError)):
            qa.rollback_new_destinations(self.scope, checkpoint, reference)
        self.assertFalse((self.root / qa.ROLLBACK_FOLDER).exists())

    def test_changed_but_valid_sqlite_snapshot_detected_before_copy(self):
        from mtr_host_request_store import HostRequestStore
        _, checkpoint, _, reference, _, _ = self.prepare_upgraded()
        path = self.scope.location("backups", "outbox")
        db = HostRequestStore(path)
        db.prepare_request(
            principal=qa._qa_principal(), request_id="e" * 32,
            payload=qa._payload("e" * 32), base_revision=7,
            current_server_revision=7, prepare_key="qa-valid-tamper",
            explicit_manual_action=True)
        self.assertEqual(qa._independent_sqlite_readback(path, "outbox")[
            "sqliteIntegrity"], "ok")
        with self.assertRaises(base.QABackupDenied):
            qa.rollback_new_destinations(self.scope, checkpoint, reference)
        self.assertFalse((self.root / qa.ROLLBACK_FOLDER).exists())

    def test_duplicate_preexisting_rollback_folder_refused_without_overwrite(self):
        _, checkpoint, _, reference, _, _ = self.prepare_upgraded()
        target_dir = self.root / qa.ROLLBACK_FOLDER
        target_dir.mkdir()
        marker = target_dir / "outbox.sqlite3"
        marker.write_bytes(b"preexisting-disposable-sentinel")
        with self.assertRaises(FileExistsError):
            qa.rollback_new_destinations(self.scope, checkpoint, reference)
        self.assertEqual(marker.read_bytes(), b"preexisting-disposable-sentinel")
        self.assertFalse((target_dir / "dispatch.sqlite3").exists())

    def test_second_rollback_invocation_refused_and_first_copy_remains_exact(self):
        _, checkpoint, _, reference, _, _ = self.prepare_upgraded()
        original = qa.rollback_new_destinations(self.scope, checkpoint, reference)
        with self.assertRaises(FileExistsError):
            qa.rollback_new_destinations(self.scope, checkpoint, reference)
        for kind in base.NAMES:
            self.assertEqual(base._sha(
                self.root / qa.ROLLBACK_FOLDER / (kind + ".sqlite3")),
                original[kind]["sha256"])

    def test_backup_symlink_is_rejected_before_rollback(self):
        _, checkpoint, _, reference, _, _ = self.prepare_upgraded()
        source = self.scope.location("backups", "peer")
        other = self.root / "qa-synthetic-alt-peer.sqlite3"
        other.write_bytes(source.read_bytes())
        source.unlink()
        try:
            source.symlink_to(other)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink privilege unavailable")
        with self.assertRaisesRegex(base.QABackupDenied,
                                    "linked_or_junction_path"):
            qa.rollback_new_destinations(self.scope, checkpoint, reference)
        self.assertFalse((self.root / qa.ROLLBACK_FOLDER).exists())

    def test_restore_target_symlink_denied_without_modifying_target(self):
        _, checkpoint, _, reference, _, _ = self.prepare_upgraded()
        target_dir = self.root / qa.ROLLBACK_FOLDER
        target_dir.mkdir()
        target = target_dir / "peer.sqlite3"
        sentinel = self.root / "only-synthetic-sentinel.txt"
        sentinel.write_text("not overwritten", encoding="utf-8")
        try:
            target.symlink_to(sentinel)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink privilege unavailable")
        with self.assertRaises(FileExistsError):
            qa.rollback_new_destinations(self.scope, checkpoint, reference)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "not overwritten")

    def test_create_only_exact_copy_rejects_symlink_and_existing_file(self):
        _, checkpoint, _, reference, _, _ = self.prepare_upgraded()
        checkpoint_file = self.scope.location("backups", "outbox")
        target = self.root / "qa-only-rollback-target.sqlite3"
        target.write_bytes(b"no-overwrite")
        with self.assertRaises(FileExistsError):
            qa._copy_exact_new(
                checkpoint_file, target, reference["outbox"]["sha256"])
        self.assertEqual(target.read_bytes(), b"no-overwrite")
        target.unlink()
        with self.assertRaisesRegex(
                qa.RollbackDenied, "original_checkpoint_has_changed_before_copy"):
            qa._copy_exact_new(checkpoint_file, target, "0" * 64)
        self.assertFalse(target.exists())

    def test_extra_or_duplicate_backup_files_block_rollback_preflight(self):
        _, checkpoint, _, reference, _, _ = self.prepare_upgraded()
        extra = self.root / "backups" / "peer-duplicate.sqlite3"
        extra.write_bytes(self.scope.location("backups", "peer").read_bytes())
        with self.assertRaisesRegex(base.QABackupDenied,
                                    "backup_missing_extra_or_duplicate_file"):
            qa.rollback_new_destinations(self.scope, checkpoint, reference)
        self.assertFalse((self.root / qa.ROLLBACK_FOLDER).exists())

    def test_main_cli_completes_without_release_permission(self):
        command = qa.ROOT / "scripts" / "qa_mtr_synthetic_upgrade_rollback_20261110.py"
        result = subprocess.run(
            [sys.executable, "-B", str(command)],
            capture_output=True, text=True, timeout=45,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        output = json.loads(result.stdout.strip())
        self.assertTrue(output["exactOriginalSnapshotDigestRestored"])
        self.assertTrue(output["priorDispatchReplayDenied"])
        self.assertTrue(output["freshDispatchAfterRollbackDenied"])
        self.assertTrue(output["sourceArtifactPinsVerified"])
        self.assertFalse(output["realInstallerExecuted"])
        self.assertFalse(output["mayInstall"])
        self.assertEqual(output["releaseDecision"], "NO_GO")
        self.assertEqual(output["signingPolicy"], "UNSIGNED_QA_ONLY")
        self.assertFalse(output["realCrossAppActorBindingVerified"])
        self.assertFalse(output["threeDatabaseAtomicEpochVerified"])
        self.assertFalse(output["officialFinancialReceiptVerified"])


if __name__ == "__main__":
    unittest.main()
