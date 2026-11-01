"""Side-by-side baseline comparison for the installer preflight pilot.

The baseline script is read from a fixed Git commit and executed only on
disposable profile trees. We deliberately do not exercise the old drive-root
bug because doing so on a mounted volume would be unsafe.
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
CURRENT_SCRIPT = ROOT / "scripts" / "Madar-Upgrade-Preflight.ps1"
BASELINE_SHA = "fbe86e6c9c74c0988a8652e734888221ed6c43e5"


def _invoke(script: Path, data: Path, backup: Path) -> subprocess.CompletedProcess:
    command = (
        "function Get-Process { @() }; "
        f"& '{script}' -DataRoot '{data}' "
        f"-BackupRoot '{backup}' -TargetVersion '1.0.2'"
    )
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        capture_output=True, text=True, timeout=35,
    )


def _file_bytes(folder: Path) -> dict[str, bytes]:
    return {
        p.relative_to(folder).as_posix(): p.read_bytes()
        for p in folder.rglob("*")
        if p.is_file()
    }


def _archive_bytes(folder: Path) -> dict[str, bytes]:
    archives = list(folder.glob("Madar-Before-1.0.2-*.zip"))
    if len(archives) != 1:
        raise AssertionError(f"Expected one snapshot, got {len(archives)}")
    with ZipFile(archives[0]) as archive:
        if archive.testzip() is not None:
            raise AssertionError("Corrupt ZIP member")
        return {
            entry.filename.replace("\\", "/"): archive.read(entry)
            for entry in archive.infolist()
            if not entry.is_dir()
        }


class CodexUpgradeParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        baseline = subprocess.run(
            ["git", "show", f"{BASELINE_SHA}:scripts/Madar-Upgrade-Preflight.ps1"],
            cwd=ROOT, capture_output=True, check=True,
        )
        cls.baseline_source = baseline.stdout

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory(prefix="madar-codex-parity-")
        self.addCleanup(self._temp.cleanup)
        self.base = Path(self._temp.name)
        self.old_script = self.base / "baseline-preflight.ps1"
        self.old_script.write_bytes(self.baseline_source)

    def test_nested_unicode_profile_matches_baseline_archive_contents(self):
        outputs = []
        for label, script in (("baseline", self.old_script),
                              ("current", CURRENT_SCRIPT)):
            root = self.base / label / "Roaming" / "MadarDesk"
            root.mkdir(parents=True)
            nested = root / "attachments" / "سند"
            nested.mkdir(parents=True)
            (nested / "invoice.bin").write_bytes(b"\0\xff\0synthetic")
            (root / "tasks.json").write_text('{"projects":[],"tasks":[]}', encoding="utf-8")
            (root / "empty-dir").mkdir()
            original = _file_bytes(root)
            backups = self.base / label / "Snapshots"
            run = _invoke(script, root, backups)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("BACKUP_VERIFIED:", run.stdout)
            self.assertEqual(_file_bytes(root), original)
            archive = _archive_bytes(backups)
            self.assertEqual(archive, original)
            outputs.append(archive)
        self.assertEqual(outputs[0], outputs[1])

    def test_missing_profile_has_same_no_backup_behavior(self):
        for label, script in (("baseline", self.old_script),
                              ("current", CURRENT_SCRIPT)):
            root = self.base / label / "Roaming" / "MadarDesk"
            backups = self.base / label / "Snapshots"
            run = _invoke(script, root, backups)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("FRESH_PROFILE:", run.stdout)
            self.assertFalse(backups.exists())
            self.assertFalse(root.exists())

    def test_overlapping_backup_path_rejected_by_both(self):
        for label, script in (("baseline", self.old_script),
                              ("current", CURRENT_SCRIPT)):
            root = self.base / label / "Roaming" / "MadarDesk"
            root.mkdir(parents=True)
            (root / "tasks.json").write_text("{}", encoding="utf-8")
            original = _file_bytes(root)
            backups = root / "nested-backup"
            run = _invoke(script, root, backups)
            self.assertNotEqual(run.returncode, 0)
            self.assertIn("Backup path overlaps user data", run.stderr)
            self.assertEqual(_file_bytes(root), original)
            self.assertFalse(backups.exists())


if __name__ == "__main__":
    unittest.main()
