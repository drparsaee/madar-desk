"""1.0.12 cumulative release contract against disposable profiles only.

Does not build any binaries, publish GitHub releases or touch live APPDATA.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
PREFLIGHT = SCRIPTS / "Madar-Upgrade-Preflight.ps1"
ACTIVATE = SCRIPTS / "Madar-Activate-Version.ps1"
INNO = SCRIPTS / "madar-update.iss"
BUILD_112 = SCRIPTS / "build_integrated_v112.py"
PREVIOUS = ("1.0.5", "1.0.6", "1.0.9", "1.0.10", "1.0.11")


def shell(script: Path, *args: str):
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
         "Bypass", "-File", str(script), *args],
        capture_output=True, text=True, timeout=40,
    )


def contents(root: Path):
    return {file.relative_to(root).as_posix(): file.read_bytes()
            for file in root.rglob("*") if file.is_file()}


@unittest.skipUnless(sys.platform == "win32", "Windows PowerShell 5.1 required")
class Cumulative112UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="madar-upgrade-112-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        # This pattern is accepted by preflight's explicitly isolated QA gate.
        self.qa = self.root / ".qa-inno-v112-cumulative"
        self.profile = self.qa / "Roaming" / "MadarDesk"
        self.profile.mkdir(parents=True)
        (self.profile / "tasks.json").write_text(
            json.dumps({"cards": [{"id": "synthetic-order", "title": "job"}]}),
            encoding="utf-8")
        (self.profile / "attachment.dat").write_bytes(b"synthetic-private-attachment")
        ledger = self.profile / "standalone-accounting.sqlite3"
        with closing(sqlite3.connect(ledger)) as db, db:
            db.execute("CREATE TABLE ledger (id INTEGER PRIMARY KEY, rial INTEGER NOT NULL)")
            db.execute("INSERT INTO ledger(rial) VALUES (987654321)")
        (self.profile / "standalone-accounting.sqlite3-wal").write_bytes(b"synthetic-wal")
        (self.profile / "standalone-accounting.sqlite3-shm").write_bytes(b"synthetic-shm")
        self.host = self.root / "ProgramData" / "MadarHost"
        self.host.mkdir(parents=True)
        (self.host / "host-config.json").write_bytes(b"synthetic-host")
        self.local = self.root / "Local" / "MadarDesk"
        self.local.mkdir(parents=True)
        (self.local / "profile.json").write_bytes(b"synthetic-local")
        self.backup = self.qa / "Snapshots"
        self.backup.mkdir(parents=True)
        (self.backup / "older-finance-backup.zip").write_bytes(b"synthetic-backup")
        self.install = self.qa / "Programs" / "MadarDesk"
        self.install.mkdir(parents=True)
        self.target = self.install / "versions" / "1.0.12" / "Madar-Desk.exe"
        self.target.parent.mkdir(parents=True)
        self.original_target = b"MZsynthetic-complete-v112-binary"
        self.target.write_bytes(self.original_target)

    def previous(self, version: str):
        old = self.install / "versions" / version / "Madar-Desk.exe"
        old.parent.mkdir(parents=True, exist_ok=True)
        old.write_bytes(b"MZold-" + version.encode("ascii"))
        (self.install / "current-version.txt").write_text(version + "\n", encoding="ascii")
        return old

    def activate(self, version="1.0.12", expected=None, extra=()):
        executable = self.install / "versions" / version / "Madar-Desk.exe"
        checksum = expected or hashlib.sha256(executable.read_bytes()).hexdigest()
        return shell(ACTIVATE, "-InstallRoot", str(self.install),
                     "-Version", version, "-ExpectedSHA256", checksum, *extra)

    def test_direct_one_step_upgrade_105_106_and_109_preserves_all_synthetic_data(self):
        for version in PREVIOUS:
            with self.subTest(installed=version):
                old = self.previous(version)
                before = {"profile": contents(self.profile), "host": contents(self.host),
                          "local": contents(self.local), "backup": contents(self.backup)}
                old_bytes = old.read_bytes()
                saved = shell(PREFLIGHT, "-DataRoot", str(self.profile),
                              "-BackupRoot", str(self.backup),
                              "-TargetVersion", "1.0.12", "-IsolatedQA")
                self.assertEqual(saved.returncode, 0, saved.stdout + saved.stderr)
                self.assertIn("BACKUP_VERIFIED", saved.stdout)
                result = self.activate()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual((self.install / "current-version.txt").read_text().strip(), "1.0.12")
                self.assertEqual((self.install / "previous-version.txt").read_text().strip(), version)
                self.assertEqual(old.read_bytes(), old_bytes)
                self.assertEqual(self.target.read_bytes(), self.original_target)
                self.assertEqual(contents(self.profile), before["profile"])
                self.assertEqual(contents(self.host), before["host"])
                self.assertEqual(contents(self.local), before["local"])
                for name, blob in before["backup"].items():
                    self.assertEqual((self.backup / name).read_bytes(), blob)
                archives = list(self.backup.glob("Madar-Before-1.0.12-*.zip"))
                self.assertTrue(archives)
                with ZipFile(archives[-1]) as archive:
                    self.assertIsNone(archive.testzip())
                    self.assertEqual({name: archive.read(name) for name in before["profile"]},
                                     before["profile"])

    def test_refuses_downgrade_or_corrupt_new_binary_and_reinstall_is_idempotent(self):
        self.previous("1.0.9")
        self.assertEqual(self.activate().returncode, 0)
        before = contents(self.install)
        self.assertEqual(self.activate().returncode, 0)
        self.assertEqual(contents(self.install), before)
        self.assertNotEqual(self.activate("1.0.9").returncode, 0)
        self.assertEqual(contents(self.install), before)
        self.assertEqual(self.activate("1.0.9", extra=("-AllowRollback",)).returncode, 0)
        self.assertEqual((self.install / "current-version.txt").read_text().strip(), "1.0.9")
        self.target.write_bytes(b"MZtampered")
        fail = self.activate(expected=hashlib.sha256(self.original_target).hexdigest())
        self.assertNotEqual(fail.returncode, 0)
        self.assertEqual((self.install / "current-version.txt").read_text().strip(), "1.0.9")


class Cumulative112SourceContract(unittest.TestCase):
    def test_metadata_and_default_build_exactly_112(self):
        import madar_update
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
        self.assertEqual((package["version"], lock["version"],
                          lock["packages"][""]["version"], madar_update.CURRENT_VERSION),
                         ("1.0.12",) * 4)
        self.assertIn("scripts/build_integrated_v112.py", package["scripts"]["dist:rc"])
        self.assertEqual(package["scripts"]["dist"], "npm run dist:rc")
        self.assertTrue(BUILD_112.is_file())

    def test_build_refuses_mismatch_without_invoking_binary_build(self):
        import sys as _sys
        _sys.path.insert(0, str(SCRIPTS))
        try:
            import build_integrated_v112 as release
        finally:
            _sys.path.remove(str(SCRIPTS))
        self.assertEqual(release.builder.VERSION, "1.0.12")
        self.assertEqual(release.builder.PROD.name, "Madar-Desk-1.0.12-Setup.exe")
        self.assertEqual(release.builder.QA.name, "Madar-Desk-1.0.12-Setup-QA.exe")
        self.assertEqual(release.MANIFEST.name, "Madar-Desk-1.0.12-Setup.release.json")
        with tempfile.TemporaryDirectory(prefix="madar-build-metadata-112-") as temporary:
            package = Path(temporary) / "package.json"
            updater = Path(temporary) / "madar_update.py"
            lock = Path(temporary) / "package-lock.json"
            package.write_text('{"version":"1.0.12","scripts":{"dist:rc":"python scripts/build_integrated_v112.py"}}', encoding="utf8")
            updater.write_text('CURRENT_VERSION = "1.0.12"', encoding="utf8")
            lock.write_text('{"version":"1.0.12","packages":{"":{"version":"1.0.12"}}}',
                            encoding="utf8")
            release.validate_source_metadata(package, updater, lock)
            updater.write_text('CURRENT_VERSION = "1.0.9"', encoding="utf8")
            with self.assertRaisesRegex(ValueError, "CURRENT_VERSION"):
                release.validate_source_metadata(package, updater, lock)
            updater.write_text('CURRENT_VERSION = "1.0.12"', encoding="utf8")
            lock.write_text('{"version":"1.0.9","packages":{"":{"version":"1.0.12"}}}',
                            encoding="utf8")
            with self.assertRaisesRegex(ValueError, "package-lock"):
                release.validate_source_metadata(package, updater, lock)

    def test_immutable_installer_contract_and_accepted_update_metadata(self):
        import madar_update
        inno = INNO.read_text(encoding="utf-8")
        self.assertIn("onlyifdoesntexist", inno)
        self.assertIn('DestDir: "{app}\\versions\\{#MadarVersion}"', inno)
        self.assertNotIn('DestDir: "{userappdata}', inno)
        self.assertNotIn('DestDir: "{commonappdata}', inno)
        self.assertIn("Madar-Upgrade-Preflight.ps1", inno)
        blob = b"MZ" + b"synthetic-installer-112" * 30
        filename = "Madar-Desk-1.0.12-Setup.exe"
        url = ("https://github.com/" + madar_update.REPOSITORY +
               "/releases/download/v1.0.12/" + filename)
        document = {"tag_name": "v1.0.12", "draft": False, "prerelease": False,
                    "assets": [{"name": filename, "browser_download_url": url,
                                "digest": "sha256:" + hashlib.sha256(blob).hexdigest(),
                                "size": len(blob)}]}
        self.assertTrue(madar_update.inspect_release(document, installed="1.0.5")["available"])
        self.assertTrue(madar_update.inspect_release(document, installed="1.0.6")["available"])
        self.assertFalse(madar_update.inspect_release(document, installed="1.0.12")["available"])
        self.assertFalse(madar_update.inspect_release(document, installed="1.0.13")["available"])


if __name__ == "__main__":
    unittest.main()
