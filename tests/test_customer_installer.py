"""Isolated Windows customer installer checks, with process guard mocked.

No real APPDATA, installed software, services, or live data are used.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parent.parent
INSTALLER = ROOT / "scripts" / "Install-Madar-Customer.ps1"
EXE = "Madar-Desk-v1.0.0-Customer-20261028.exe"


class CustomerInstallTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="madar-installer-isolated-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.package = self.root / "package"
        self.package.mkdir()
        self.install = self.root / "install"
        self.data = self.root / "appdata" / "MadarDesk"
        self.backups = self.root / "archive"
        (self.data / "attachments").mkdir(parents=True)
        (self.data / "tasks.json").write_text('{"tasks":["customer-task"]}', encoding="utf8")
        (self.data / "identity.bin").write_bytes(b"\x00private\xff")
        (self.data / "attachments" / "asset.bin").write_bytes(b"attachment\x00payload")
        self.original = {p.relative_to(self.data).as_posix(): p.read_bytes()
                         for p in self.data.rglob("*") if p.is_file()}
        self.exe = self.package / EXE
        self.exe.write_bytes(b"test-executable-not-a-real-PE" * 20)
        self.write_manifest()

    def write_manifest(self):
        (self.package / "Madar-Release-Manifest.json").write_text(json.dumps({
            "version": "1.0.0", "executable": EXE,
            "sha256": hashlib.sha256(self.exe.read_bytes()).hexdigest(),
        }), encoding="utf8")

    def invoke(self, mock_processes=True):
        # A fake Get-Process is injected into the child PowerShell session so
        # the QA paths can be verified while a real RC15 user app is open.
        # The actual installer still blocks active processes.
        prefix = "function Get-Process { @() }; " if mock_processes else ""
        command = (prefix +
                   "& '" + str(INSTALLER) + "'" +
                   " -InstallRoot '" + str(self.install) + "'" +
                   " -DataRoot '" + str(self.data) + "'" +
                   " -BackupRoot '" + str(self.backups) + "'" +
                   " -PackageRoot '" + str(self.package) + "'")
        return subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                               "-Command", command], capture_output=True, text=True, timeout=35)

    def test_versioned_install_snapshots_complete_profile_and_preserves_data(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.install / "current-version.txt").read_text().strip(), "1.0.0")
        target = self.install / "versions" / "1.0.0" / "Madar-Desk.exe"
        self.assertEqual(target.read_bytes(), self.exe.read_bytes())
        self.assertTrue((self.install / "Run-Madar.cmd").exists())
        archive, = list(self.backups.glob("Madar-Profile-Before-1.0.0-*.zip"))
        with ZipFile(archive) as zipped:
            self.assertEqual({p: zipped.read(p) for p in self.original}, self.original)
        self.assertEqual({p.relative_to(self.data).as_posix(): p.read_bytes()
                          for p in self.data.rglob("*") if p.is_file()}, self.original)

    def test_tampered_package_refuses_before_writing_installed_files(self):
        self.exe.write_bytes(b"tampered")
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.install.exists())
        self.assertFalse(self.backups.exists())
        self.assertEqual((self.data / "tasks.json").read_bytes(), self.original["tasks.json"])

    def test_immutable_version_rejects_different_executable(self):
        target = self.install / "versions" / "1.0.0" / "Madar-Desk.exe"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"older-but-different-executable")
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(target.read_bytes(), b"older-but-different-executable")
        self.assertFalse(self.backups.exists())


if __name__ == "__main__":
    unittest.main()
