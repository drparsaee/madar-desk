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

    def test_activation_rejects_unmounted_drive_root_and_normalized_root(self):
        # A missing drive is deliberate: never exercise this dangerous old
        # root behavior on a mounted customer volume.
        unused = next((f"{letter}:\\"
                       for letter in "ZYXWVUTSRQPONMLKJIHGFED"
                       if not Path(f"{letter}:\\").exists()), None)
        if unused is None:
            self.skipTest("No unmounted drive letter")
        for install_root in (unused, unused + r"synthetic\.."):
            with self.subTest(root=install_root):
                result = ps_file(ACTIVATE, "-InstallRoot", install_root,
                                 "-Version", "1.0.2",
                                 "-ExpectedSHA256", digest(self.new.read_bytes()))
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("Drive root", result.stderr)
                self.assertEqual((self.install / "current-version.txt").read_text().strip(), "1.0.1")
                self.assertFalse((self.install / "previous-version.txt").exists())
                self.assertEqual({p.relative_to(self.data).as_posix(): p.read_bytes()
                                  for p in self.data.rglob("*") if p.is_file()}, self.before)

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

    def test_volume_root_paths_fail_closed_even_after_normalization(self):
        # Never pass a mounted drive's root to the old implementation: use an
        # unused volume letter that has no data to read or delete.
        unused = next((f"{letter}:\\"
                       for letter in "ZYXWVUTSRQPONMLKJIHGFED"
                       if not Path(f"{letter}:\\").exists()), None)
        if unused is None:
            self.skipTest("No unmounted drive letter")
        marker = self.base / "MustNotBeCreated"
        samples = (
            (unused, str(marker)),
            (unused + r"synthetic\..", str(marker)),
            (str(self.data), unused),
            (str(self.data), unused + r"synthetic\.."),
        )
        for data_root, backup_root in samples:
            with self.subTest(data=data_root, backup=backup_root):
                command = (
                    "function Get-Process { @() }; "
                    f"& '{PREFLIGHT}' -DataRoot '{data_root}' "
                    f"-BackupRoot '{backup_root}' -TargetVersion '1.0.2'"
                )
                result = subprocess.run(
                    ["powershell.exe", "-NoProfile", "-Command", command],
                    capture_output=True, text=True, timeout=20,
                )
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("Drive root", result.stderr)
                self.assertFalse(marker.exists())
                self.assertEqual(
                    {p.relative_to(self.data).as_posix(): p.read_bytes()
                     for p in self.data.rglob("*") if p.is_file()}, self.before)

    def test_locked_input_never_publishes_unverified_or_partial_backup(self):
        # Fail the ZIP producer safely, without a real app, customer database,
        # or manipulating the Windows user profile. No completed ZIP should
        # ever appear on the disk when an input file is unreadable.
        locked = self.data / "attachments" / "locked.bin"
        locked.write_bytes(b"synthetic-financial-attachment")
        original = {p.relative_to(self.data).as_posix(): p.read_bytes()
                    for p in self.data.rglob("*") if p.is_file()}
        backup = self.base / "NoInvalidBackups"
        command = (
            "function Get-Process { @() }; "
            f"$handle=[IO.File]::Open('{locked}',[IO.FileMode]::Open,"
            "[IO.FileAccess]::ReadWrite,[IO.FileShare]::None); "
            "try { "
            f"& '{PREFLIGHT}' -DataRoot '{self.data}' "
            f"-BackupRoot '{backup}' -TargetVersion '1.0.2'"
            " } finally { $handle.Dispose() }"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command],
            capture_output=True, text=True, timeout=35,
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("BACKUP_VERIFIED", result.stdout)
        self.assertEqual(list(backup.glob("*.zip")), [])
        self.assertEqual(list(backup.glob("*.partial")), [])
        self.assertEqual({p.relative_to(self.data).as_posix(): p.read_bytes()
                          for p in self.data.rglob("*") if p.is_file()}, original)

    def test_many_small_files_verified_once_and_archived_without_leftovers(self):
        # Characterization of the source-to-ZIP contract at a more realistic
        # attachment count; the newer index must not alter filenames/bytes.
        folder = self.data / "attachments"
        for i in range(180):
            (folder / f"synthetic-{i:04d}.txt").write_text(
                f"{i}: یک سند آزمایشی", encoding="utf-8")
        before = {p.relative_to(self.data).as_posix(): p.read_bytes()
                  for p in self.data.rglob("*") if p.is_file()}
        backup = self.base / "BulkSnapshot"
        command = (
            "function Get-Process { @() }; "
            f"& '{PREFLIGHT}' -DataRoot '{self.data}' "
            f"-BackupRoot '{backup}' -TargetVersion '1.0.2'"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("BACKUP_VERIFIED:", result.stdout)
        archives = list(backup.glob("Madar-Before-1.0.2-*.zip"))
        self.assertEqual(len(archives), 1)
        self.assertEqual(list(backup.glob("*.partial")), [])
        with ZipFile(archives[0]) as zipped:
            self.assertEqual({name: zipped.read(name) for name in before}, before)
        self.assertEqual({p.relative_to(self.data).as_posix(): p.read_bytes()
                          for p in self.data.rglob("*") if p.is_file()}, before)

    def test_two_successful_snapshots_keep_both_verified_archives(self):
        # A second run must never replace the last verified customer backup,
        # even when both snapshots happen in the same clock interval.
        backup = self.base / "RepeatedSnapshots"
        command = (
            "function Get-Process { @() }; "
            f"& '{PREFLIGHT}' -DataRoot '{self.data}' "
            f"-BackupRoot '{backup}' -TargetVersion '1.0.2'"
        )
        for _ in range(2):
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", command],
                capture_output=True, text=True, timeout=35,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("BACKUP_VERIFIED:", result.stdout)
        archives = list(backup.glob("Madar-Before-1.0.2-*.zip"))
        self.assertEqual(len(archives), 2)
        self.assertEqual(list(backup.glob("*.partial")), [])
        for archive in archives:
            with ZipFile(archive) as zipped:
                self.assertEqual({name: zipped.read(name) for name in self.before}, self.before)
        self.assertEqual({p.relative_to(self.data).as_posix(): p.read_bytes()
                          for p in self.data.rglob("*") if p.is_file()}, self.before)


if __name__ == "__main__":
    unittest.main()
