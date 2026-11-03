"""Immutable cumulative 1.0.12 source contract and disposable profile upgrade.

Never starts an EXE, installs a package, contacts GitHub, or opens real APPDATA.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from tests.test_cumulative_111_update import shell, contents, PREFLIGHT, ACTIVATE

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class Cumulative112SourceContract(unittest.TestCase):
    def test_versioned_builder_requires_all_three_source_version_markers(self):
        sys.path.insert(0, str(SCRIPTS))
        try:
            import build_integrated_v112 as release
        finally:
            sys.path.remove(str(SCRIPTS))
        self.assertEqual(release.builder.PROD.name, "Madar-Desk-1.0.12-Setup.exe")
        self.assertEqual(release.builder.QA.name, "Madar-Desk-1.0.12-Setup-QA.exe")
        self.assertEqual(release.MANIFEST.name, "Madar-Desk-1.0.12-Setup.release.json")
        with TemporaryDirectory(prefix="madar-build-112-") as folder:
            root = Path(folder)
            package, updater, lock = [root / name for name in
                                      ("package.json", "madar_update.py", "package-lock.json")]
            package.write_text(json.dumps({"version":"1.0.12", "scripts":{
                "dist:rc":"python scripts/build_integrated_v112.py"}}), encoding="utf8")
            updater.write_text('CURRENT_VERSION = "1.0.12"\n', encoding="utf8")
            lock.write_text(json.dumps({"version":"1.0.12", "packages":{
                "":{"version":"1.0.12"}}}), encoding="utf8")
            release.validate_source_metadata(package, updater, lock)
            updater.write_text('CURRENT_VERSION = "1.0.11"\n', encoding="utf8")
            with self.assertRaisesRegex(ValueError, "CURRENT_VERSION"):
                release.validate_source_metadata(package, updater, lock)

    def test_one_full_installer_for_accounting_and_task_manager(self):
        package = json.loads((ROOT / "package.json").read_text(encoding="utf8"))
        lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf8"))
        from madar_update import CURRENT_VERSION
        self.assertEqual((package["version"],lock["version"],
                          lock["packages"][""]["version"],CURRENT_VERSION),
                         ("1.0.12",)*4)
        self.assertIn("build_integrated_v112.py",package["scripts"]["dist:rc"])
        source = (SCRIPTS / "madar-update.iss").read_text(encoding="utf8")
        self.assertIn('DestDir: "{app}\\versions\\{#MadarVersion}"',source)
        self.assertIn("Madar-Upgrade-Preflight.ps1",source)
        self.assertIn("Madar-Activate-Version.ps1",source)
        self.assertNotIn('DestDir: "{userappdata}',source)


@unittest.skipUnless(sys.platform == "win32", "Windows PowerShell required")
class Cumulative112SyntheticUpgrade(unittest.TestCase):
    def test_111_to_112_with_synthetic_ledger_preserves_profile_exactly(self):
        with TemporaryDirectory(prefix="madar-upgrade-112-") as folder:
            root = Path(folder)
            qa = root / ".qa-inno-v112-integrated"
            profile = qa / "Roaming" / "MadarDesk"
            profile.mkdir(parents=True)
            (profile / "tasks.json").write_text('{"tasks":[{"id":"synthetic"}]}', encoding="utf8")
            (profile / "attachment.dat").write_bytes(b"not-a-real-user-attachment")
            ledger = profile / "standalone-accounting.sqlite3"
            with closing(sqlite3.connect(ledger)) as db, db:
                db.execute("CREATE TABLE ledger (id INTEGER, rial INTEGER NOT NULL)")
                db.execute("INSERT INTO ledger VALUES (1, 123456789)")
            (profile / "standalone-accounting.sqlite3-wal").write_bytes(b"synthetic-wal")
            (profile / "standalone-accounting.sqlite3-shm").write_bytes(b"synthetic-shm")
            snapshot = contents(profile)
            backup = qa / "Snapshots"
            backup.mkdir()
            install = qa / "Programs" / "MadarDesk"
            old = install / "versions" / "1.0.11" / "Madar-Desk.exe"
            old.parent.mkdir(parents=True)
            old.write_bytes(b"MZsynthetic-v111")
            new = install / "versions" / "1.0.12" / "Madar-Desk.exe"
            new.parent.mkdir(parents=True)
            binary = b"MZsynthetic-v112-integrated"
            new.write_bytes(binary)
            (install / "current-version.txt").write_text("1.0.11\n",encoding="ascii")
            pre = shell(PREFLIGHT,"-DataRoot",str(profile),"-BackupRoot",str(backup),
                        "-TargetVersion","1.0.12","-IsolatedQA")
            self.assertEqual(pre.returncode,0,pre.stdout+pre.stderr)
            self.assertIn("BACKUP_VERIFIED",pre.stdout)
            promoted = shell(ACTIVATE,"-InstallRoot",str(install),"-Version","1.0.12",
                             "-ExpectedSHA256",hashlib.sha256(binary).hexdigest())
            self.assertEqual(promoted.returncode,0,promoted.stdout+promoted.stderr)
            self.assertEqual((install/"current-version.txt").read_text().strip(),"1.0.12")
            self.assertEqual(old.read_bytes(),b"MZsynthetic-v111")
            self.assertEqual(contents(profile),snapshot)
            archived = list(backup.glob("Madar-Before-1.0.12-*.zip"))
            self.assertTrue(archived)
            with ZipFile(archived[-1]) as data:
                self.assertIsNone(data.testzip())
                self.assertEqual({name:data.read(name) for name in snapshot},snapshot)
            rejected = shell(ACTIVATE,"-InstallRoot",str(install),"-Version","1.0.11",
                             "-ExpectedSHA256",hashlib.sha256(old.read_bytes()).hexdigest())
            self.assertNotEqual(rejected.returncode,0)
            self.assertEqual((install/"current-version.txt").read_text().strip(),"1.0.12")


if __name__ == "__main__":
    unittest.main()
