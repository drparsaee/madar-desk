"""Disposable 1.0.4..1.0.9 installer parity, no operational data or real install."""
from __future__ import annotations

import hashlib
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
ACTIVATE = SCRIPTS / "Madar-Activate-Version.ps1"
PREFLIGHT = SCRIPTS / "Madar-Upgrade-Preflight.ps1"
INNO = SCRIPTS / "madar-update.iss"
BUILDER = SCRIPTS / "build_integrated_v109.py"
OLD_VERSIONS = ("1.0.4", "1.0.5", "1.0.6", "1.0.7", "1.0.8")


def execute(script: Path, *params: str):
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
         "Bypass", "-File", str(script), *params],
        capture_output=True, text=True, timeout=40,
    )


def snapshot(root: Path):
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in root.rglob("*") if p.is_file()}


@unittest.skipUnless(sys.platform == "win32", "Isolated PowerShell 5.1 acceptance")
class Cumulative109Acceptance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="madar-cumulative-109-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.qa = self.root / ".qa-inno-v109-cumulative"
        self.data = self.qa / "Roaming" / "MadarDesk"
        self.data.mkdir(parents=True)
        (self.data / "tasks.json").write_text(
            json.dumps({"cards": [{"id": "synthetic-card-42", "done": False}]}),
            encoding="utf-8",
        )
        for name, blob in (
            ("standalone-accounting.sqlite3-wal", b"synthetic-wal-content"),
            ("standalone-accounting.sqlite3-shm", b"synthetic-shm-content"),
            ("private-identity.json", b"synthetic-account-not-credentials"),
        ):
            (self.data / name).write_bytes(blob)
        with closing(sqlite3.connect(self.data / "standalone-accounting.sqlite3")) as db:
            with db:
                db.execute("CREATE TABLE journal (id INTEGER PRIMARY KEY, rial INTEGER NOT NULL)")
                db.execute("INSERT INTO journal (rial) VALUES (987654)")
        self.install = self.qa / "Programs" / "MadarDesk"
        self.install.mkdir(parents=True)
        self.host = self.root / "ProgramData" / "MadarHost"
        self.host.mkdir(parents=True)
        (self.host / "host-settings.json").write_bytes(b"synthetic-host")
        self.local = self.root / "Local" / "MadarDesk"
        self.local.mkdir(parents=True)
        (self.local / "cached-settings.json").write_bytes(b"synthetic-cache")
        self.backups = self.qa / "Snapshots"
        self.backups.mkdir(parents=True)
        (self.backups / "older-finance-backup.zip").write_bytes(b"synthetic-older-backup")
        self.target = self.install / "versions" / "1.0.9" / "Madar-Desk.exe"
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(b"MZcomplete-synthetic-1.0.9-binary")

    def seed_version(self, version: str):
        old = self.install / "versions" / version / "Madar-Desk.exe"
        old.parent.mkdir(parents=True)
        old.write_bytes(b"MZold-synthetic-version-" + version.encode("ascii"))
        (self.install / "current-version.txt").write_text(version + "\n", encoding="ascii")
        return old

    def activate(self, version="1.0.9", *, allow_rollback=False):
        path = self.install / "versions" / version / "Madar-Desk.exe"
        args = ["-InstallRoot", str(self.install), "-Version", version,
                "-ExpectedSHA256", hashlib.sha256(path.read_bytes()).hexdigest()]
        if allow_rollback:
            args.append("-AllowRollback")
        return execute(ACTIVATE, *args)

    def test_complete_single_update_preserves_every_104_through_108_profile(self):
        for version in OLD_VERSIONS:
            with self.subTest(previous=version):
                old = self.seed_version(version)
                expected_data = snapshot(self.data)
                expected_host = snapshot(self.host)
                expected_local = snapshot(self.local)
                expected_old = old.read_bytes()
                existing_backups = snapshot(self.backups)
                preflight = execute(
                    PREFLIGHT, "-DataRoot", str(self.data),
                    "-BackupRoot", str(self.backups), "-TargetVersion", "1.0.9",
                    "-IsolatedQA",
                )
                self.assertEqual(preflight.returncode, 0, preflight.stdout + preflight.stderr)
                self.assertIn("BACKUP_VERIFIED", preflight.stdout)
                update = self.activate()
                self.assertEqual(update.returncode, 0, update.stdout + update.stderr)
                self.assertEqual((self.install / "current-version.txt").read_text().strip(), "1.0.9")
                self.assertEqual((self.install / "previous-version.txt").read_text().strip(), version)
                self.assertEqual(old.read_bytes(), expected_old)
                self.assertEqual(snapshot(self.data), expected_data)
                self.assertEqual(snapshot(self.host), expected_host)
                self.assertEqual(snapshot(self.local), expected_local)
                for name, content in existing_backups.items():
                    self.assertEqual((self.backups / name).read_bytes(), content)
                archives = list(self.backups.glob("Madar-Before-1.0.9-*.zip"))
                self.assertTrue(archives)
                with ZipFile(archives[-1]) as zipped:
                    self.assertIsNone(zipped.testzip())
                    self.assertEqual({name: zipped.read(name) for name in expected_data}, expected_data)

    def test_activation_downgrade_rejected_explicit_verified_rollback_allowed(self):
        self.seed_version("1.0.8")
        accepted = self.activate()
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        unchanged = snapshot(self.install)
        downgrade = self.activate("1.0.8")
        self.assertNotEqual(downgrade.returncode, 0)
        self.assertEqual(snapshot(self.install), unchanged)
        rollback = self.activate("1.0.8", allow_rollback=True)
        self.assertEqual(rollback.returncode, 0, rollback.stderr)
        self.assertEqual((self.install / "current-version.txt").read_text().strip(), "1.0.8")

    def test_109_reinstall_is_idempotent_and_corruption_does_not_activate(self):
        self.seed_version("1.0.6")
        self.assertEqual(self.activate().returncode, 0)
        before = snapshot(self.install)
        self.assertEqual(self.activate().returncode, 0)
        self.assertEqual(snapshot(self.install), before)
        self.target.write_bytes(b"MZbad-109-payload")
        corrupted = execute(
            ACTIVATE, "-InstallRoot", str(self.install), "-Version", "1.0.9",
            "-ExpectedSHA256", hashlib.sha256(b"MZcomplete-synthetic-1.0.9-binary").hexdigest(),
        )
        self.assertNotEqual(corrupted.returncode, 0)
        self.assertEqual((self.install / "current-version.txt").read_text().strip(), "1.0.9")

    def test_semantic_version_guard_not_lexical_and_no_broken_old_symlink(self):
        self.seed_version("1.0.8")
        self.assertEqual(self.activate().returncode, 0)
        newer = self.install / "versions" / "1.0.10" / "Madar-Desk.exe"
        newer.parent.mkdir(parents=True)
        newer.write_bytes(b"MZsynthetic-1.0.10")
        promote = self.activate("1.0.10")
        self.assertEqual(promote.returncode, 0, promote.stderr)
        before = snapshot(self.install)
        older = self.activate("1.0.9")
        self.assertNotEqual(older.returncode, 0)
        self.assertEqual(snapshot(self.install), before)


class Cumulative109PackagingContract(unittest.TestCase):
    def test_current_release_metadata_remains_aligned_after_109(self):
        from madar_update import CURRENT_VERSION
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
        self.assertEqual((package["version"], lock["version"],
                          lock["packages"][""]["version"], CURRENT_VERSION),
                         ("1.0.12",) * 4)
        self.assertIn("scripts/build_integrated_v112.py", package["scripts"]["dist:rc"])
        self.assertEqual(package["scripts"]["dist"], "npm run dist:rc")

    def test_powershell_release_scripts_parse(self):
        for script in (ACTIVATE, PREFLIGHT):
            command = (
                "$tokens=$null; $errors=$null; "
                "[System.Management.Automation.Language.Parser]::ParseFile("
                "'" + str(script).replace("'", "''") + "',"
                "[ref]$tokens,[ref]$errors)|Out-Null; "
                "if($errors.Count -gt 0){$errors|Out-String|Write-Error; exit 1}"
            )
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_full_executable_instead_of_patch_and_immutable_version(self):
        content = INNO.read_text(encoding="utf-8")
        self.assertIn('DestDir: "{app}\\versions\\{#MadarVersion}"', content)
        self.assertIn("onlyifdoesntexist", content)
        self.assertIn("Madar-Upgrade-Preflight.ps1", content)
        self.assertIn("Madar-Activate-Version.ps1", content)
        self.assertNotIn('DestDir: "{userappdata}', content)
        self.assertNotIn('DestDir: "{commonappdata}', content)
        self.assertNotIn('DestDir: "{localappdata}\\MadarDesk', content)
        self.assertTrue(BUILDER.is_file(), "Cumulative 1.0.9 build entry point missing")
        builder = BUILDER.read_text(encoding="utf-8")
        self.assertIn('builder.VERSION = "1.0.9"', builder)
        self.assertIn("build_p0_release_candidate", builder)
        self.assertIn("CURRENT_VERSION", builder)

    def test_integrated_build_rejects_stale_or_mismatched_update_metadata(self):
        import sys as _sys
        _sys.path.insert(0, str(SCRIPTS))
        try:
            import build_integrated_v109 as release
        finally:
            _sys.path.remove(str(SCRIPTS))
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            package = parent / "package.json"
            updater = parent / "madar_update.py"
            package.write_text('{"version": "1.0.9"}', encoding="utf-8")
            updater.write_text('CURRENT_VERSION = "1.0.9"\n', encoding="utf-8")
            release.validate_source_metadata(package, updater)
            package.write_text('{"version": "1.0.8"}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "package.json"):
                release.validate_source_metadata(package, updater)
            package.write_text('{"version": "1.0.9"}', encoding="utf-8")
            updater.write_text('CURRENT_VERSION = "1.0.6"\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "CURRENT_VERSION"):
                release.validate_source_metadata(package, updater)
        self.assertEqual(release.builder.PROD.name, "Madar-Desk-1.0.9-Setup.exe")

    def test_updater_accepts_matching_github_metadata_for_109(self):
        import madar_update
        blob = b"MZ" + b"synthetic-update" * 45
        filename = "Madar-Desk-1.0.9-Setup.exe"
        url = "https://github.com/drparsaee/madar-desk-updates/releases/download/v1.0.9/" + filename
        info = madar_update.inspect_release({
            "tag_name": "v1.0.9", "draft": False, "prerelease": False,
            "assets": [{"name": filename, "browser_download_url": url,
                        "digest": "sha256:" + hashlib.sha256(blob).hexdigest(),
                        "size": len(blob)}],
        }, installed="1.0.8")
        self.assertTrue(info["available"])
        self.assertEqual(info["filename"], filename)
        self.assertFalse(madar_update.inspect_release({"tag_name": "v1.0.9"},
                                                      installed="1.0.9")["available"])


if __name__ == "__main__":
    unittest.main()
