"""Safe upgrade contract, using only disposable data and binaries.

Never touches the machine's installed Madar or real APPDATA.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from zipfile import ZipFile

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
PREFLIGHT = SCRIPTS / "Madar-Upgrade-Preflight.ps1"
ACTIVATE = SCRIPTS / "Madar-Activate-Version.ps1"


def ps_file(script: Path, *pairs: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(script), *pairs],
        capture_output=True, text=True, timeout=35)


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="madar-version-update-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.data = self.base / "Roaming" / "MadarDesk"
        self.data.mkdir(parents=True)
        (self.data / "attachments").mkdir()
        (self.data / "tasks.json").write_text(
            json.dumps({"projects": ["customer"], "tasks": ["must-persist"]}), encoding="utf8")
        (self.data / "attachments" / "proof.bin").write_bytes(b"\x00customer-attachment\xff")
        self.before = {p.relative_to(self.data).as_posix(): p.read_bytes()
                       for p in self.data.rglob("*") if p.is_file()}
        self.install = self.base / "Programs" / "MadarDesk"
        self.install.mkdir(parents=True)
        self.old = self.install / "versions" / "1.0.1" / "Madar-Desk.exe"
        self.new = self.install / "versions" / "1.0.2" / "Madar-Desk.exe"
        self.old.parent.mkdir(parents=True)
        self.new.parent.mkdir(parents=True)
        self.old.write_bytes(b"signed-or-unsigned-v101-test-binary")
        self.new.write_bytes(b"signed-or-unsigned-v102-test-binary")
        (self.install / "current-version.txt").write_text("1.0.1\n", encoding="ascii")

    def test_preflight_takes_full_verified_snapshot_without_mutating_data(self):
        backups = self.base / "ReleaseBackups"
        # The real machine can be running the installed Madar while we test
        # snapshot logic against a disposable root. Mock only the external
        # process enumerator in this QA PowerShell process; never weaken the
        # production preflight that must refuse an active application.
        command = (
            "function Get-Process { @() }; "
            f"& '{PREFLIGHT}' -DataRoot '{self.data}' "
            f"-BackupRoot '{backups}' -TargetVersion '1.0.2'"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command],
            capture_output=True, text=True, timeout=35)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        archive, = list(backups.glob("Madar-Before-1.0.2-*.zip"))
        with ZipFile(archive) as zipped:
            self.assertIsNone(zipped.testzip())
            self.assertEqual({name: zipped.read(name) for name in self.before}, self.before)
        self.assertEqual({p.relative_to(self.data).as_posix(): p.read_bytes()
                          for p in self.data.rglob("*") if p.is_file()}, self.before)

    def test_switch_is_atomic_reversible_and_data_never_touched(self):
        arg = ["-InstallRoot", str(self.install), "-Version", "1.0.2",
               "-ExpectedSHA256", digest(self.new.read_bytes())]
        result = ps_file(ACTIVATE, *arg)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.install / "current-version.txt").read_text().strip(), "1.0.2")
        self.assertEqual((self.install / "previous-version.txt").read_text().strip(), "1.0.1")
        same_version = ps_file(ACTIVATE, *arg)
        self.assertEqual(same_version.returncode, 0, same_version.stdout + same_version.stderr)
        self.assertEqual((self.install / "previous-version.txt").read_text().strip(), "1.0.1")
        rollback = ps_file(ACTIVATE, "-InstallRoot", str(self.install),
                           "-Version", "1.0.1",
                           "-ExpectedSHA256", digest(self.old.read_bytes()))
        self.assertEqual(rollback.returncode, 0, rollback.stdout + rollback.stderr)
        self.assertEqual((self.install / "current-version.txt").read_text().strip(), "1.0.1")
        self.assertTrue(self.old.is_file() and self.new.is_file())
        self.assertEqual({p.relative_to(self.data).as_posix(): p.read_bytes()
                          for p in self.data.rglob("*") if p.is_file()}, self.before)

    def test_corrupted_new_binary_blocks_activation(self):
        result = ps_file(ACTIVATE, "-InstallRoot", str(self.install),
                         "-Version", "1.0.2", "-ExpectedSHA256", "0" * 64)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.install / "current-version.txt").read_text().strip(), "1.0.1")
        self.assertFalse((self.install / "previous-version.txt").exists())
        self.assertEqual(self.new.read_bytes(), b"signed-or-unsigned-v102-test-binary")

    def test_running_madar_refuses_snapshot_before_any_changes(self):
        backups = self.base / "MustNotExist"
        # Fake a writer without launching Madar or touching real user data.
        command = (
            "function Get-Process { [pscustomobject]@{ProcessName='Madar-Desk-live'} }; "
            f"& '{PREFLIGHT}' -DataRoot '{self.data}' "
            f"-BackupRoot '{backups}' -TargetVersion '1.0.2'"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command],
            capture_output=True, text=True, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Close all Madar", result.stderr)
        self.assertFalse(backups.exists())
        self.assertEqual({p.relative_to(self.data).as_posix(): p.read_bytes()
                          for p in self.data.rglob("*") if p.is_file()}, self.before)


if __name__ == "__main__":
    unittest.main()
