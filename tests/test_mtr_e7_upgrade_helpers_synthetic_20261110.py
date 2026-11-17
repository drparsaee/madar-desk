"""Actual Windows PowerShell upgrade-helper tests on disposable synthetic paths.

No installer EXE, Windows service, Madar process, network or real user data is
accessed. Both scripts are read-only source inputs. All helper *arguments* and
all writable environment directories are within a newly created, unlinked
TemporaryDirectory named .qa-inno-v123-<random>. Never use an operational path.

Run: py -3.12 -B -m unittest -v tests.test_mtr_e7_upgrade_helpers_synthetic_20261110
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile


REPO = Path(__file__).resolve().parents[1]
PREFLIGHT = REPO / "scripts" / "Madar-Upgrade-Preflight.ps1"
ACTIVATE = REPO / "scripts" / "Madar-Activate-Version.ps1"
QA_NAME = re.compile(r"\.qa-inno-v123-[A-Za-z0-9_-]+\Z", re.ASCII)
SHA256 = re.compile(r"[a-f0-9]{64}\Z", re.ASCII)
PS = shutil.which("powershell.exe") if sys.platform == "win32" else None


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_link(path: Path) -> bool:
    if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except FileNotFoundError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


@unittest.skipUnless(sys.platform == "win32" and PS, "Windows PowerShell required")
class MtrE7UpgradeHelpersSynthetic(unittest.TestCase):
    def setUp(self):
        # All writes remain in a newly created, owned, random QA tree.
        sandbox = tempfile.TemporaryDirectory(prefix=".qa-inno-v123-")
        self.addCleanup(sandbox.cleanup)
        self.root = Path(sandbox.name).absolute()
        self.assertTrue(self.root.is_dir())
        self.assertRegex(self.root.name, QA_NAME)
        self.assertFalse(any(is_link(part) for part in (self.root, *self.root.parents)))
        self.assertTrue(PREFLIGHT.is_file())
        self.assertTrue(ACTIVATE.is_file())
        self.helper_hashes = {
            PREFLIGHT: digest(PREFLIGHT.read_bytes()),
            ACTIVATE: digest(ACTIVATE.read_bytes()),
        }

        self.data = self.root / "Roaming" / "MadarDesk"
        self.backups = self.root / "Snapshots"
        self.install = self.root / "Programs" / "MadarDesk"
        self.environment = self.root / "TestEnvironment"
        for name in ("AppData", "LocalAppData", "Profile", "Temp", "WebView2"):
            (self.environment / name).mkdir(parents=True, exist_ok=True)
        self.env = os.environ.copy()
        self.env.update({
            "APPDATA": str(self.environment / "AppData"),
            "LOCALAPPDATA": str(self.environment / "LocalAppData"),
            "USERPROFILE": str(self.environment / "Profile"),
            "HOME": str(self.environment / "Profile"),
            "TEMP": str(self.environment / "Temp"),
            "TMP": str(self.environment / "Temp"),
            "WEBVIEW2_USER_DATA_FOLDER": str(self.environment / "WebView2"),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        self.addCleanup(self.assert_helpers_unchanged)

    def assert_helpers_unchanged(self):
        for source, previous in self.helper_hashes.items():
            self.assertEqual(digest(source.read_bytes()), previous,
                             "Actual PowerShell helper source must remain unchanged")

    def confined(self, path: Path, *, require_no_link: bool = True) -> Path:
        """Validate every subprocess path *before* passing it to PowerShell."""
        self.assertIsInstance(path, Path)
        self.assertTrue(path.is_absolute())
        self.assertTrue(path.is_relative_to(self.root))
        self.assertNotEqual(path, self.root)
        self.assertFalse(any(part in ("..", ".") for part in path.parts))
        for candidate in (path, *path.parents):
            if require_no_link:
                self.assertFalse(is_link(candidate),
                                 "No helper argument may traverse a link/junction")
            if candidate == self.root:
                break
        return path

    def call_helper(self, script: Path, args: list[str], *, paths: tuple[Path, ...],
                    synthetic_link_path: Path | None = None):
        self.assertIn(script, (PREFLIGHT, ACTIVATE))
        for path in paths:
            if path == synthetic_link_path:
                # Only a deliberate link NEGATIVE inside the same disposable
                # root may bypass the harness's default no-link guard. The
                # link target must be synthetic too, never a real profile.
                self.confined(path, require_no_link=False)
                self.assertTrue(path.resolve(strict=False).is_relative_to(self.root))
                self.assertTrue(is_link(path))
            else:
                self.confined(path)
        proc = subprocess.run(
            [
                PS, "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
                "Bypass", "-File", str(script), *args,
            ],
            cwd=self.root,
            env=self.env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=25,
            check=False,
        )
        return proc

    def preflight(
        self, *, data: Path | None = None, backups: Path | None = None,
        version: str = "1.0.23", synthetic_backup_link: bool = False,
    ):
        data = self.data if data is None else data
        backups = self.backups if backups is None else backups
        self.assertEqual(
            data,
            self.root / "Roaming" / "MadarDesk",
            "Only the generated .qa-inno-v123-*/Roaming/MadarDesk is authorized",
        )
        return self.call_helper(
            PREFLIGHT,
            ["-DataRoot", str(data), "-BackupRoot", str(backups),
             "-TargetVersion", version, "-IsolatedQA"],
            paths=(data, backups),
            synthetic_link_path=backups if synthetic_backup_link else None,
        )

    def executable(self, version: str, payload: bytes) -> Path:
        self.assertRegex(version, r"^1\.0\.(?:22|23)$")
        target = self.confined(
            self.install / "versions" / version / "Madar-Desk.exe")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        return target

    def activate(self, version: str, expected_digest: str, *, rollback: bool = False,
                 install: Path | None = None):
        install = self.install if install is None else install
        arguments = [
            "-InstallRoot", str(install), "-Version", version,
            "-ExpectedSHA256", expected_digest,
        ]
        if rollback:
            arguments.append("-AllowRollback")
        return self.call_helper(ACTIVATE, arguments, paths=(install,))

    def versions(self) -> tuple[Path, Path]:
        return (self.install / "current-version.txt",
                self.install / "previous-version.txt")

    def assert_failed_without_pointer_change(self, result, before=None):
        self.assertNotEqual(result.returncode, 0,
                            "Unsafe activation/preflight must fail closed")
        pointers = self.versions()
        for path, expected in zip(pointers, before or (None, None)):
            self.assertEqual(path.read_bytes() if path.exists() else None, expected)

    def test_backup_exact_zip_sha_and_file_readback(self):
        expected = {
            "cards.json": b'{"cards":[{"id":"synthetic-only"}]}',
            "nested/historical.txt": "sample \u0645\u062f\u0627\u0631".encode("utf-8"),
            "nested/blob.dat": bytes(range(256)) * 3,
        }
        for relative, content in expected.items():
            target = self.data / Path(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        result = self.preflight()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("BACKUP_VERIFIED:", result.stdout)
        backups = list(self.backups.glob("Madar-Before-1.0.23-*.zip"))
        self.assertEqual(len(backups), 1)
        self.assertFalse(list(self.backups.glob("*.partial")))
        with zipfile.ZipFile(backups[0], "r") as archive:
            actual = {info.filename: archive.read(info) for info in archive.infolist()
                      if not info.is_dir()}
            self.assertEqual(set(actual), set(expected))
            for relative, content in expected.items():
                self.assertEqual(len(actual[relative]), len(content))
                self.assertEqual(digest(actual[relative]), digest(content))
                self.assertEqual(actual[relative], content)
            self.assertIsNone(archive.testzip())
        for relative, content in expected.items():
            self.assertEqual((self.data / relative).read_bytes(), content)

    def test_empty_first_run_never_creates_backup(self):
        self.assertFalse(self.data.exists())
        result = self.preflight()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("FRESH_PROFILE", result.stdout)
        self.assertFalse(self.backups.exists())
        self.assertFalse(self.data.exists())

    def test_backup_overlapping_data_root_refuses_before_archiving(self):
        (self.data / "keep.txt").parent.mkdir(parents=True)
        (self.data / "keep.txt").write_bytes(b"unchanged")
        # Only synthetic paths. Their overlap must be denied by the helper.
        for candidate in (self.data, self.data / "NestedBackups",
                          self.root / "Roaming"):
            with self.subTest(backup=candidate.name):
                result = self.preflight(backups=candidate)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertEqual((self.data / "keep.txt").read_bytes(), b"unchanged")
                self.assertFalse(list(self.root.rglob("Madar-Before-*.zip")))

    def test_isolated_qa_rejects_nonsibling_backup_inside_disposable_root(self):
        # All paths are still strictly within this new disposable temp root.
        # QA must use the exact sibling root QA_ROOT/Snapshots, not any other
        # arbitrary writable folder (production installer convention).
        (self.data / "keep.txt").parent.mkdir(parents=True)
        (self.data / "keep.txt").write_bytes(b"synthetic-only")
        alternate = self.confined(self.root / "OtherBackups")
        result = self.preflight(backups=alternate)
        self.assertNotEqual(result.returncode, 0,
                            "QA out-of-sibling backup location must be denied")
        self.assertFalse(alternate.exists(), "Rejected QA path must not be created")
        self.assertFalse(self.backups.exists())
        self.assertEqual((self.data / "keep.txt").read_bytes(), b"synthetic-only")

    def test_actual_preflight_rejects_wrong_synthetic_qa_data_root(self):
        # Bypass ONLY the harness's exact-name helper for a negative test;
        # the script still receives exclusively freshly generated temp paths.
        wrong = self.confined(self.root / "Roaming" / "NotMadarDesk")
        wrong.mkdir(parents=True)
        (wrong / "data.txt").write_bytes(b"synthetic-witness")
        result = self.call_helper(
            PREFLIGHT,
            ["-DataRoot", str(wrong), "-BackupRoot", str(self.backups),
             "-TargetVersion", "1.0.23", "-IsolatedQA"],
            paths=(wrong, self.backups),
        )
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertFalse(self.backups.exists())
        self.assertEqual((wrong / "data.txt").read_bytes(), b"synthetic-witness")

    def test_backup_rejects_reparse_inside_synthetic_data(self):
        self.data.mkdir(parents=True)
        target = self.root / "LinkTarget"
        target.mkdir()
        (target / "witness.txt").write_bytes(b"outside-data-but-still-synthetic")
        linked = self.data / "linked-folder"
        try:
            linked.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("Creating test symlink requires Windows privileges: " + str(exc))
        result = self.preflight()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertFalse(list(self.backups.glob("*.zip")))
        self.assertEqual((target / "witness.txt").read_bytes(),
                         b"outside-data-but-still-synthetic")

    def test_backup_rejects_linked_snapshots_root_without_writing_target(self):
        self.data.mkdir(parents=True)
        (self.data / "keep.txt").write_bytes(b"synthetic-backup-input")
        destination = self.root / "OtherSyntheticDestination"
        destination.mkdir()
        try:
            self.backups.symlink_to(destination, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("Creating test symlink requires Windows privileges: " + str(exc))
        result = self.preflight(synthetic_backup_link=True)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertFalse(list(destination.glob("Madar-Before-*.zip")))
        self.assertEqual((self.data / "keep.txt").read_bytes(),
                         b"synthetic-backup-input")

    def test_activation_hash_upgrades_and_same_version_are_idempotent(self):
        old_bytes = b"synthetic-v122-not-an-executable"
        new_bytes = b"synthetic-v123-not-an-executable"
        self.executable("1.0.22", old_bytes)
        self.executable("1.0.23", new_bytes)
        current, previous = self.versions()
        first = self.activate("1.0.22", digest(old_bytes))
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertEqual(current.read_text(encoding="utf-8-sig").strip(), "1.0.22")
        self.assertFalse(previous.exists())

        upgrade = self.activate("1.0.23", digest(new_bytes))
        self.assertEqual(upgrade.returncode, 0, upgrade.stdout + upgrade.stderr)
        self.assertEqual(current.read_text(encoding="utf-8-sig").strip(), "1.0.23")
        self.assertEqual(previous.read_text(encoding="utf-8-sig").strip(), "1.0.22")
        before = previous.read_bytes()
        repeat = self.activate("1.0.23", digest(new_bytes))
        self.assertEqual(repeat.returncode, 0, repeat.stdout + repeat.stderr)
        self.assertIn("VERSION_ALREADY_ACTIVE", repeat.stdout)
        self.assertEqual(previous.read_bytes(), before)

    def test_refuse_downgrade_until_explicit_rollback_with_digest(self):
        old_bytes = b"older-real-path-never-used; synthetic payload"
        new_bytes = b"newer-real-path-never-used; synthetic payload"
        self.executable("1.0.22", old_bytes)
        self.executable("1.0.23", new_bytes)
        current, previous = self.versions()
        first = self.activate("1.0.23", digest(new_bytes))
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        original = current.read_bytes()
        denied = self.activate("1.0.22", digest(old_bytes))
        self.assert_failed_without_pointer_change(denied, (original, None))
        self.assertIn("requires explicit rollback", denied.stdout + denied.stderr)
        permitted = self.activate("1.0.22", digest(old_bytes), rollback=True)
        self.assertEqual(permitted.returncode, 0, permitted.stdout + permitted.stderr)
        self.assertEqual(current.read_text(encoding="utf-8-sig").strip(), "1.0.22")
        self.assertEqual(previous.read_text(encoding="utf-8-sig").strip(), "1.0.23")

    def test_activation_rejects_wrong_digest_missing_target_and_invalid_version(self):
        new_bytes = b"synthetic-binary-do-not-launch"
        self.executable("1.0.23", new_bytes)
        self.assert_failed_without_pointer_change(
            self.activate("1.0.23", digest(b"different bytes")))
        # There is no 1.0.22 binary in this fixture yet.
        self.assert_failed_without_pointer_change(
            self.activate("1.0.22", digest(b"missing")))
        self.assert_failed_without_pointer_change(
            self.activate("1.0.23/../../escape", digest(new_bytes)))
        self.assertFalse(list(self.root.rglob("current-version.txt")))

    def test_activation_blocks_malformed_previous_pointer(self):
        original = b"synthetic-current-version"
        proposed = b"synthetic-proposed-version"
        self.executable("1.0.22", original)
        self.executable("1.0.23", proposed)
        current, previous = self.versions()
        current.write_text("../outside\n", encoding="utf-8")
        before = current.read_bytes()
        self.assert_failed_without_pointer_change(
            self.activate("1.0.23", digest(proposed)), (before, None))
        self.assertFalse(previous.exists())

    def test_activation_rejects_linked_pointer_without_following_it(self):
        proposed = b"synthetic-proposed-version"
        self.executable("1.0.23", proposed)
        current, previous = self.versions()
        target = self.root / "OutsideInstallRootButStillSynthetic.txt"
        target.write_bytes(b"do-not-change")
        try:
            current.symlink_to(target)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("Creating test symlink requires Windows privileges: " + str(exc))
        denied = self.activate("1.0.23", digest(proposed))
        self.assertNotEqual(denied.returncode, 0, denied.stdout)
        self.assertEqual(target.read_bytes(), b"do-not-change")
        self.assertFalse(previous.exists())

    def test_disallow_any_subprocess_path_outside_generated_fixture(self):
        # These are Python-level guards; dangerous paths never reach PowerShell.
        for unsafe in (
            REPO / "scripts", self.root.parent,
            self.root / ".." / "outside",
            Path(self.root.anchor),
        ):
            with self.subTest(path=str(unsafe)):
                with self.assertRaises(AssertionError):
                    self.activate("1.0.23", digest(b"irrelevant"),
                                  install=unsafe)
        with self.assertRaises(AssertionError):
            self.preflight(data=self.root / "Roaming" / "AnotherApp")
        # Argument validation is before process invocation.
        self.assertFalse(self.backups.exists())
        self.assertFalse(self.install.exists())


if __name__ == "__main__":
    unittest.main()
