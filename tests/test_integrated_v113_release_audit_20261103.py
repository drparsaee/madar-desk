"""Pure synthetic release/verifier tests. No build, installer or native app launch."""
from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
import json
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch, Mock
from zipfile import ZipFile

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import build_integrated_v113 as release  # noqa: E402
import qa_integrated_v113_installer as installer  # noqa: E402
import qa_integrated_v113_native as native  # noqa: E402
sys.path.remove(str(SCRIPTS))

GIT_COMMIT = "b" * 40


class Release113SyntheticAudit(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="madar-113-manifest-synthetic-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.release = self.root / "release"
        self.release.mkdir()
        self.program = self.release / "Madar-Desk-v1.0.13-Cumulative-20261103.exe"
        self.qa = self.release / "Madar-Desk-1.0.13-Setup-QA.exe"
        self.prod = self.release / "Madar-Desk-1.0.13-Setup.exe"
        self.prerequisite = self.release / "webview2-test-prereq.exe"
        self.program.write_bytes(b"MZ-synthetic-113-APP-no-real-binary")
        self.qa.write_bytes(b"MZ-synthetic-113-QA-no-real-installer")
        self.prod.write_bytes(b"MZ-synthetic-113-PROD-no-real-installer")
        self.prerequisite.write_bytes(b"MZ-synthetic-Microsoft-prerequisite-placeholder")
        self.manifest = self.release / "Madar-Desk-1.0.13-Setup.release.json"
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        builder = release.builder
        for attr, value in {
                "ROOT": self.root, "RELEASE": self.release,
                "PROGRAM": self.program, "QA": self.qa, "PROD": self.prod,
                "PREREQ": self.prerequisite,
                "QA_ROOT": self.root / ".qa-inno-v113-integrated"}.items():
            self.patches.enter_context(patch.object(builder, attr, value))
        self.patches.enter_context(patch.object(release, "MANIFEST", self.manifest))

    def descriptor(self):
        return release.release_descriptor(GIT_COMMIT)

    def test_manifest_pins_three_distinct_binaries_and_prerequisite(self):
        descriptor = self.descriptor()
        release.verify_release_descriptor(descriptor, source_commit=GIT_COMMIT)
        self.assertEqual(descriptor["schema"], 2)
        self.assertEqual(descriptor["sourceGitCommit"], GIT_COMMIT)
        self.assertEqual(descriptor["cumulativeFrom"][-1], "1.0.12")
        for filename, key, bytes_key in (
                (self.program, "applicationSha256", "applicationBytes"),
                (self.qa, "qaInstallerSha256", "qaInstallerBytes"),
                (self.prod, "installerSha256", "installerBytes")):
            self.assertEqual(descriptor[key], release.digest(filename))
            self.assertEqual(descriptor[bytes_key], filename.stat().st_size)
        self.assertNotEqual(descriptor["installerSha256"], descriptor["qaInstallerSha256"])

    def test_tampered_qa_binary_rejected_before_execution(self):
        descriptor = self.descriptor()
        self.qa.write_bytes(b"MZ-synthetic-113-QA-TAMPERED-BOUNDARY")
        with self.assertRaisesRegex(RuntimeError, "SHA256/size/PE.*QA"):
            release.verify_release_descriptor(descriptor)

    def test_misnamed_or_production_exe_substituted_for_qa_rejected(self):
        descriptor = self.descriptor()
        self.qa.write_bytes(self.prod.read_bytes())
        forged = dict(descriptor, qaInstallerSha256=release.digest(self.qa),
                      qaInstallerBytes=self.qa.stat().st_size)
        with self.assertRaisesRegex(RuntimeError, "installers must be distinct"):
            release.verify_release_descriptor(forged)
        forged["qaInstaller"] = "Madar-Desk-1.0.13-Setup.exe"
        with self.assertRaisesRegex(RuntimeError, "artifact identity"):
            release.verify_release_descriptor(forged)

    def test_tampered_program_prod_and_prerequisite_rejected(self):
        for target, name in ((self.program, "APP"), (self.prod, "PROD"),
                             (self.prerequisite, "PREREQ")):
            with self.subTest(name=name):
                original = target.read_bytes()
                desc = self.descriptor()
                target.write_bytes(original + b"tamper")
                with self.assertRaisesRegex(RuntimeError,
                                            "SHA256/size/PE|prerequisite differs"):
                    release.verify_release_descriptor(desc)
                target.write_bytes(original)

    def test_malformed_or_legacy_descriptor_rejected(self):
        descriptor = self.descriptor()
        candidates = [
            dict(descriptor, schema=1),
            dict(descriptor, sourceGitCommit="fake"),
            dict(descriptor, sourceGitCommit="a" * 40),
            dict(descriptor, installerBytes=True),
            dict(descriptor, qaInstallerSha256="no-hash"),
            dict(descriptor, cumulativeFrom=["1.0.11"]),
        ]
        for i, payload in enumerate(candidates):
            with self.subTest(candidate=i):
                with self.assertRaises(RuntimeError):
                    release.verify_release_descriptor(payload, source_commit=GIT_COMMIT)

    def test_read_manifest_gates_qa_before_any_install_or_profile_write(self):
        self.manifest.write_text(json.dumps(self.descriptor()), encoding="utf-8")
        with patch.object(release, "source_git_commit", return_value=GIT_COMMIT):
            self.assertEqual(release.read_verified_release_descriptor()["schema"], 2)
            self.qa.write_bytes(self.qa.read_bytes() + b"tamper")
            with patch.object(installer.subprocess, "run", side_effect=AssertionError(
                    "An invalid QA installer must never launch")):
                with self.assertRaisesRegex(RuntimeError, "SHA256/size/PE"):
                    installer.main()
        self.assertFalse(release.builder.QA_ROOT.exists(),
                         "Failed QA verification must not create any QA profile")

    def test_full_qa_runner_control_flow_with_mocked_installer_and_synthetic_profile(self):
        """Do NOT execute Inno: emulate only expected output files in temp."""
        self.manifest.write_text(json.dumps(self.descriptor()), encoding="utf-8")
        receipt = self.release / "Madar-Desk-1.0.13-Setup-QA.acceptance.json"
        qa_root = release.builder.QA_ROOT

        def fake_inno_command(command, **_kwargs):
            self.assertEqual(command[0], str(self.qa))
            self.assertIn("/DIR=" + str(qa_root / "Programs" / "MadarDesk"), command)
            self.assertNotIn(str(self.root / "RealAPPDATA"), " ".join(command))
            profile = qa_root / "Roaming" / "MadarDesk"
            target = qa_root / "Programs" / "MadarDesk"
            installed = target / "versions" / "1.0.13" / "Madar-Desk.exe"
            installed.parent.mkdir(parents=True)
            installed.write_bytes(self.program.read_bytes())
            (target / "current-version.txt").write_text("1.0.13\n", encoding="utf-8")
            (target / "previous-version.txt").write_text("1.0.12\n", encoding="utf-8")
            backups = qa_root / "Snapshots"
            backups.mkdir()
            with ZipFile(backups / "Madar-Before-1.0.13-SYNTHETIC.zip", "w") as archive:
                for file in profile.rglob("*"):
                    if file.is_file():
                        archive.write(file, arcname=file.relative_to(profile).as_posix())
            (qa_root / "qa-installer.log").write_text("synthetic Inno QA log", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with patch.object(release, "source_git_commit", return_value=GIT_COMMIT), \
             patch.object(installer, "ACCEPTANCE", receipt), \
             patch.object(installer.subprocess, "run", side_effect=fake_inno_command) as proc:
            installer.main()
            self.assertEqual(proc.call_count, 1)
        self.assertFalse(qa_root.exists(), "Disposable synthetic QA directory must be cleaned")
        report = json.loads(receipt.read_text(encoding="utf-8"))
        self.assertEqual(report["upgradeFrom"], "1.0.12")
        self.assertEqual(report["upgradeTo"], "1.0.13")
        self.assertTrue(report["previousProgramUnchanged"])
        self.assertTrue(report["qaDirectoryRemoved"])
        self.assertEqual(report["qaInstallerSha256"], release.digest(self.qa))
        self.assertEqual(report["syntheticProfileFileCount"],
                         report["verifiedBackupFileCount"])

    def test_native_runner_verifies_exact_manifest_before_popen(self):
        self.manifest.write_text(json.dumps(self.descriptor()), encoding="utf-8")
        self.program.write_bytes(self.program.read_bytes() + b"tamper")
        with patch.object(release, "source_git_commit", return_value=GIT_COMMIT):
            with patch.object(subprocess, "Popen", side_effect=AssertionError(
                    "A tampered packaged app must never execute")):
                with self.assertRaisesRegex(RuntimeError, "SHA256/size/PE"):
                    native.main()

    def test_fixed_qa_root_rejects_any_arbitrary_path(self):
        good = release.builder.QA_ROOT
        installer.assert_disposable_qa_root(good)
        for path in (self.root / "Roaming" / "MadarDesk",
                     self.root / ".qa-inno-v113-other",
                     self.root.parent / "MadarDesk"):
            with self.subTest(path=path):
                with self.assertRaisesRegex(RuntimeError, "not the fixed isolated root"):
                    installer.assert_disposable_qa_root(path)

    def test_qa_root_symlink_denied_if_supported(self):
        good = release.builder.QA_ROOT
        target = self.root / "empty-qa-target"
        target.mkdir()
        try:
            good.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Windows symlink privilege not available")
        with self.assertRaisesRegex(RuntimeError, "link/junction"):
            installer.assert_disposable_qa_root(good)

    def test_git_clean_commit_and_dirty_or_malformed_source(self):
        clean = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        head = subprocess.CompletedProcess([], 0, stdout=GIT_COMMIT + "\n", stderr="")
        with patch.object(release.subprocess, "run", side_effect=[clean, head]) as run:
            self.assertEqual(release.source_git_commit(self.root), GIT_COMMIT)
            self.assertEqual(run.call_count, 2)
        dirty = subprocess.CompletedProcess([], 0, stdout=" M src/something.jsx\n", stderr="")
        with patch.object(release.subprocess, "run", side_effect=[dirty, head]):
            with self.assertRaisesRegex(RuntimeError, "uncommitted"):
                release.source_git_commit(self.root)
        malformed_head = subprocess.CompletedProcess([], 0, stdout="garbage\n", stderr="")
        with patch.object(release.subprocess, "run", side_effect=[clean, malformed_head]):
            with self.assertRaisesRegex(RuntimeError, "full Git SHA"):
                release.source_git_commit(self.root)

    def test_native_environment_scopes_home_temp_profile_and_scrubs_config(self):
        env = native.synthetic_environment(self.root, {
            "APPDATA": "C:\\Users\\Real\\AppData\\Roaming",
            "LOCALAPPDATA": "C:\\Users\\Real\\AppData\\Local",
            "USERPROFILE": "C:\\Users\\Real", "HOMEDRIVE": "C:",
            "HOMEPATH": "\\Users\\Real", "HOME": "C:\\Users\\Real",
            "MADAR_SECRET": "real", "PARSIAN_PASSWORD": "real",
            "ACCOUNTING_DB": "real", "SQLSERVER_CONNECTION": "real",
            "PYTHONPATH": "C:\\Users\\Real\\modules", "PATH": "synthetic-path"})
        self.assertEqual(env["APPDATA"], str(self.root / "Roaming"))
        self.assertEqual(env["LOCALAPPDATA"], str(self.root / "Local"))
        self.assertEqual(env["USERPROFILE"], str(self.root / "UserProfile"))
        self.assertEqual(env["HOME"], env["USERPROFILE"])
        self.assertEqual(env["HOMEDRIVE"] + env["HOMEPATH"], env["USERPROFILE"])
        self.assertEqual(env["TEMP"], str(self.root / "Temp"))
        self.assertEqual(env["TMP"], str(self.root / "Temp"))
        self.assertEqual(env["PATH"], "synthetic-path")
        for key in ("MADAR_SECRET", "PARSIAN_PASSWORD", "ACCOUNTING_DB",
                    "SQLSERVER_CONNECTION", "PYTHONPATH"):
            self.assertNotIn(key, env)

    def test_builder_refuses_existing_release_without_build(self):
        self.manifest.write_text("{}", encoding="utf-8")
        with patch.object(release, "validate_source_metadata"):
            with patch.object(release.builder, "main", side_effect=AssertionError(
                    "builder.main must not run when a release exists")):
                with self.assertRaisesRegex(FileExistsError, "already exists"):
                    release.main()

    def test_builder_refuses_stale_sha_sidecar_without_build(self):
        for target in (self.program, self.qa, self.prod):
            target.unlink()
        sidecar = self.release / (self.qa.name + ".sha256.txt")
        sidecar.write_text("stale fake receipt", encoding="utf-8")
        with patch.object(release, "validate_source_metadata"):
            with patch.object(release.builder, "main", side_effect=AssertionError(
                    "Immutable partial release must not build")):
                with self.assertRaisesRegex(FileExistsError, "already exists"):
                    release.main()


if __name__ == "__main__":
    unittest.main()
