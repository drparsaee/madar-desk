"""Bounded synthetic-only tests for the real isolated Madar Inno acceptance.

Never launch installed Madar, setup, or rollback in this unittest suite.
The separate CLI already executed the real QA-only Inno and synthetic rollback;
these tests inspect its saved evidence and exercise negative guards.
"""
from __future__ import annotations

from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZIP_DEFLATED


SCRIPT = Path(__file__).resolve().parents[1] / (
    "scripts/qa_madar_v127_upgrade_acceptance_20261110.py")
spec = importlib.util.spec_from_file_location("madar_v127_sterile_acceptance", SCRIPT)
qa = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(qa)


class SyntheticUpgradeAcceptanceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(
            dir=r"D:\CoS-Test", prefix="madar-v127-acceptance-fixture-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def _mock_qa_paths(self):
        private = self.root / "bounded-qa" / ".qa-inno-v127-synthetic"
        program = private / "Programs" / "MadarDesk"
        roaming = private / "Roaming" / "MadarDesk"
        snapshots = private / "Snapshots"
        stack = ExitStack()
        stack.enter_context(patch.object(qa, "QA_DATA", private))
        stack.enter_context(patch.object(qa, "QA_PROGRAM", program))
        stack.enter_context(patch.object(qa, "QA_ROAMING", roaming))
        stack.enter_context(patch.object(qa, "QA_SNAPSHOTS", snapshots))
        return stack, private, program, roaming, snapshots

    def test_pinned_actual_qa_executables_and_hardened_script(self):
        self.assertEqual(qa.sha_file(qa.QA_SETUP), qa.QA_SETUP_SHA)
        self.assertEqual(qa.sha_file(qa.QA_ISS), qa.QA_ISS_SHA)
        self.assertEqual(qa.sha_file(qa.QA_ACTIVATE), qa.QA_ACTIVATE_SHA)
        self.assertEqual(qa.sha_file(qa.OLD_PE), qa.OLD_PE_SHA)
        manifest = qa.read_json(qa.QA_MANIFEST)
        self.assertEqual(manifest["version"], "1.0.27")
        self.assertEqual(manifest["setup"]["signatureStatus"], "NotSigned")
        self.assertFalse(manifest["installerExecuted"])
        self.assertFalse(manifest["signed"])

    def test_real_installed_program_remains_v126_readonly(self):
        before = qa.installed_readonly_snapshot()
        self.assertEqual(before["current"], "1.0.26")
        self.assertEqual(before["previous"], "1.0.23")
        self.assertEqual(before["exeSha256"], qa.REAL_V126_SHA)
        self.assertEqual(before["onlyProgramFilesRead"], True)
        self.assertNotEqual(Path(before["root"]), qa.QA_PROGRAM)

    def test_no_setup_or_rollback_command_can_target_real_install(self):
        log = qa.QA_RUN / "sterile-QA-test.log"
        cmd = qa.installer_command(log)
        self.assertEqual(cmd[0], str(qa.QA_SETUP))
        self.assertIn("/DIR=" + str(qa.QA_PROGRAM), cmd)
        self.assertIn("/LOG=" + str(log), cmd)
        self.assertNotIn("C:\\Users\\Parsa\\AppData\\Local\\Programs\\MadarDesk", cmd)
        with self.assertRaises(qa.AcceptanceBlocked):
            qa.installer_command(self.root / "not-approved.log")
        with self.assertRaises(qa.AcceptanceBlocked):
            qa.installer_command(log, install_dir=Path(
                r"C:\Users\Parsa\AppData\Local\Programs\MadarDesk"))
        rollback = qa.rollback_command()
        self.assertIn("-AllowRollback", rollback)
        self.assertEqual(rollback[rollback.index("-InstallRoot") + 1],
                         str(qa.QA_PROGRAM))
        self.assertEqual(rollback[rollback.index("-ExpectedSHA256") + 1],
                         qa.OLD_PE_SHA)

    def test_create_only_synthetic_profile_and_three_sqlite_dbs(self):
        stack, private, program, roaming, _ = self._mock_qa_paths()
        private.parent.mkdir(parents=True)
        with stack:
            fingerprints = qa.create_synthetic_profile()
            self.assertEqual(len(fingerprints), 6)
            self.assertEqual(qa.synthetic_digest_map(), fingerprints)
            self.assertEqual(qa.sha_file(
                program / "versions" / "1.0.26" / "Madar-Desk.exe"),
                qa.OLD_PE_SHA)
            self.assertEqual(qa.read_version(program / "current-version.txt"),
                             "1.0.26")
            for database in ("tasks", "collab", "finance"):
                db = roaming / "db" / (database + ".sqlite")
                connection = sqlite3.connect(str(db))
                try:
                    marker = connection.execute(
                        "SELECT marker FROM synthetic_probe").fetchone()[0]
                finally:
                    connection.close()
                self.assertEqual(marker, "qa-only-" + database)
            with self.assertRaises(qa.AcceptanceBlocked):
                qa.create_synthetic_profile()

    def test_independent_hash_verified_synthetic_backup_and_tamper_rejection(self):
        stack, private, _, roaming, snapshots = self._mock_qa_paths()
        private.parent.mkdir(parents=True)
        with stack:
            original = qa.create_synthetic_profile()
            snapshots.mkdir(exist_ok=False)
            archive = snapshots / "Madar-Before-1.0.27-synthetic.zip"
            with ZipFile(archive, "x", compression=ZIP_DEFLATED) as zipfile:
                for name in sorted(original):
                    zipfile.write(roaming / name, arcname=name)
            verified = qa.verify_snapshot(original)
            self.assertEqual(verified["count"], 1)
            self.assertTrue(verified["independentHashReadback"])
            self.assertEqual(verified["archives"][0]["files"], 6)
            # One broken archive is not accepted, even when another is good.
            second = snapshots / "Madar-Before-1.0.27-corrupt.zip"
            with ZipFile(second, "x", compression=ZIP_DEFLATED) as zipfile:
                zipfile.writestr("tasks.json", "changed")
            with self.assertRaises(qa.AcceptanceBlocked):
                qa.verify_snapshot(original)
            # Even without corrupt archives, changed data must fail.
            second.unlink()
            (roaming / "tasks.json").write_text("tampered", encoding="utf-8")
            with self.assertRaises(qa.AcceptanceBlocked):
                qa.verify_snapshot(original)

    def test_multiple_create_only_verified_backups_supported_after_retry(self):
        stack, private, _, roaming, snapshots = self._mock_qa_paths()
        private.parent.mkdir(parents=True)
        with stack:
            original = qa.create_synthetic_profile()
            snapshots.mkdir(exist_ok=False)
            for suffix in ("one", "two"):
                archive = snapshots / ("Madar-Before-1.0.27-" + suffix + ".zip")
                with ZipFile(archive, "x", compression=ZIP_DEFLATED) as zipfile:
                    for name in sorted(original):
                        zipfile.write(roaming / name, arcname=name)
            evidence = qa.verify_snapshot(original)
            self.assertEqual(evidence["count"], 2)
            self.assertNotEqual(evidence["archives"][0]["path"],
                                evidence["archives"][1]["path"])

    def test_actual_qa_failed_first_preflight_and_rejected_dir_override(self):
        prior = qa.read_json(qa.QA_RUN / "acceptance-e204b0b93d12" /
                             "qa-upgrade-acceptance.json")
        self.assertEqual(prior["status"], "BLOCKED")
        self.assertEqual(prior["positiveQaInstall"]["exitCode"], 7)
        self.assertEqual(prior["negativeDir"]["exitCode"], 7)
        positive_log = (qa.QA_RUN / "acceptance-e204b0b93d12" /
                        "positive-qa-install.log").read_text(encoding="utf-8-sig")
        negative_log = (qa.QA_RUN / "acceptance-e204b0b93d12" /
                        "negative-dir.log").read_text(encoding="utf-8-sig")
        self.assertIn("PrepareToInstall failed", positive_log)
        self.assertIn("QA ONLY: invalid installation destination", negative_log)

    def test_real_qa_retry_rollback_and_all_backups_verified(self):
        report_file = (qa.QA_RUN / "acceptance-rollback-4b08673d53e3" /
                       "qa-upgrade-recovery.json")
        report = qa.read_json(report_file)
        self.assertEqual(report["status"],
                         "QA_RETRY_INSTALL_AND_SYNTHETIC_ROLLBACK_VERIFIED_WITH_PREFLIGHT_BLOCKER")
        self.assertEqual(report["rollback"]["exitCode"], 0)
        self.assertEqual(report["rolledBackTo"], "1.0.26")
        self.assertTrue(report["firstPreflightIntermittenceUnresolved"])
        self.assertTrue(report["backupBeforeRollback"]["independentHashReadback"])
        self.assertTrue(report["backupAfterRollback"]["independentHashReadback"])
        self.assertEqual(report["backupAfterRollback"]["count"], 2)
        self.assertEqual(report["installedBefore"], report["installedAfter"])
        self.assertFalse(report["productionInstallAttempted"])
        self.assertFalse(report["releaseApproved"])
        self.assertEqual(qa.read_version(qa.QA_PROGRAM / "current-version.txt"),
                         "1.0.26")
        self.assertEqual(qa.sha_file(
            qa.QA_PROGRAM / "versions" / "1.0.27" / "Madar-Desk.exe"), qa.QA_APP_SHA)
        self.assertEqual(qa.synthetic_digest_map(), report["syntheticBefore"])

    def test_resumption_is_not_replayable_after_rollback(self):
        with self.assertRaisesRegex(qa.AcceptanceBlocked,
                                    "synthetic QA upgrade state inconsistent"):
            qa.resume_qa_from_verified_retry()

    def test_fresh_qa_inno_first_pass_install_backup_and_rollback(self):
        fresh = qa.ROOT / "fresh-acceptance-004cd12bdcfd"
        summary = qa.read_json(fresh / "fresh-acceptance-result.json")
        self.assertEqual(summary["status"],
                         "QA_ISOLATED_INNO_INSTALL_BACKUP_ROLLBACK_VERIFIED")
        self.assertEqual(summary["negativeDir"]["exitCode"], 7)
        self.assertEqual(summary["positiveQaInstall"]["exitCode"], 0)
        self.assertEqual(summary["qaRollback"]["exitCode"], 0)
        self.assertEqual(summary["qaInstalledExeSha256"], qa.QA_APP_SHA)
        self.assertEqual(summary["qaRollbackToVersion"], "1.0.26")
        self.assertTrue(summary["syntheticSQLiteHandlesClosedBeforeInno"])
        self.assertEqual(summary["verifiedPreupgradeBackup"]["count"], 1)
        self.assertEqual(summary["verifiedPostRollbackBackup"]["count"], 1)
        self.assertEqual(summary["installedBefore"], summary["installedAfter"])
        self.assertEqual(summary["installedAfter"]["exeSha256"],
                         qa.REAL_V126_SHA)
        self.assertFalse(summary["productionInstallAttempted"])
        self.assertFalse(summary["realLedgerTouched"])
        self.assertFalse(summary["realUserProfileTouched"])
        self.assertFalse(summary["networkServiceModified"])
        path = Path(summary["freshCandidateSetupPath"])
        self.assertEqual(qa.sha_file(path), summary["freshCandidateSetupSha256"])
        data = (fresh / ".qa-inno-v127-20261110")
        self.assertEqual(qa.read_version(
            data / "Programs/MadarDesk/current-version.txt"), "1.0.26")
        self.assertEqual(qa.sha_file(data / "Programs/MadarDesk/versions/1.0.27/"
                                       "Madar-Desk.exe"), qa.QA_APP_SHA)

    def test_cli_and_commands_never_install_in_production_or_run_real_gui(self):
        code = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('"productionInstallAttempted": False', code)
        self.assertIn('"realLedgerTouched": False', code)
        self.assertIn('"realUserProfileTouched": False', code)
        self.assertIn('"releaseApproved": False', code)
        self.assertNotIn("Start-Process", code)
        self.assertNotIn("git commit", code)
        self.assertNotIn("--noconfirm", code)


if __name__ == "__main__":
    unittest.main()
