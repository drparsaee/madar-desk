"""Read-only E7 CLI negatives against disposable synthetic Git fixtures only."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "tools" / "mtr_release_readiness.py"
MARKER = ".mtr-release-readiness-fixture.json"
PREREQ = ("release/.madar-inno-prereq/"
          "MicrosoftEdgeWebView2RuntimeInstallerX64.exe")
SOURCES = (
    "scripts/build_integrated_v123.py",
    "scripts/build_p0_release_candidate.py",
    "scripts/sync_font.py",
    "scripts/madar-update.iss",
    "scripts/Madar-Upgrade-Preflight.ps1",
    "scripts/Madar-Activate-Version.ps1",
    "scripts/qa_p0_v123_webview2.py",
    "native_app.py",
    "assets/madar.ico",
)


def write(root: Path, relative: str, data: str | bytes) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        target.write_bytes(data)
    else:
        target.write_text(data, encoding="utf-8")


def git(root: Path, *args) -> None:
    result = subprocess.run(["git", "-C", str(root), *args],
                            capture_output=True, text=True, timeout=10)
    if result.returncode:
        raise AssertionError("synthetic git setup failed: " + result.stderr)


def fixture(root: Path) -> None:
    write(root, MARKER, json.dumps(
        {"owner": "mtr-release-readiness", "synthetic": True}))
    write(root, ".gitignore", "release/\ndist/\n")
    write(root, "package.json", json.dumps({
        "version": "1.0.23", "scripts": {"dist:rc":
        "python -B scripts/build_integrated_v123.py --webview2 " + PREREQ}
    }))
    write(root, "package-lock.json", json.dumps({
        "version": "1.0.23", "packages": {"": {"version": "1.0.23"}}
    }))
    write(root, "madar_update.py", 'CURRENT_VERSION = "1.0.23"\n')
    for name in SOURCES:
        if name == "scripts/build_integrated_v123.py":
            value = 'builder.VERSION = "1.0.23"\n'
        elif name.endswith(".ico"):
            value = b"synthetic-test-only-not-a-valid-executable"
        else:
            value = "# synthetic fixture source only\n"
        write(root, name, value)
    rows = [
        "# E7 disposable fixture matrix",
        "| ID | Outcome | Gate |",
        "|---|---|---|",
    ]
    for prefix, count in (("AC", 32), ("G", 8)):
        rows.extend(f"| {prefix}-{index:02} | synthetic | OPEN |"
                    for index in range(1, count + 1))
    write(root, "docs/modernization/MTR_E7_ACCEPTANCE_GATES_20261109.md",
          "\n".join(rows) + "\n")
    git(root, "init", "-q")
    # Match CLI's explicitly disabled global Git config and avoid machine
    # core.autocrlf preferences creating false synthetic dirty states.
    git(root, "config", "--local", "core.autocrlf", "false")
    git(root, "-c", "user.name=Synthetic", "-c",
        "user.email=synthetic@example.invalid", "add", ".")
    git(root, "-c", "user.name=Synthetic", "-c",
        "user.email=synthetic@example.invalid", "commit", "-qm", "synthetic baseline")
    write(root, PREREQ, b"fake fixture bytes; unsigned and not usable")


class ReadOnlyReleaseReadinessTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="mtr-e7-fixture-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        fixture(self.root)

    def invoke(self, root=None):
        path = str(self.root if root is None else root)
        result = subprocess.run(
            [sys.executable, "-B", str(CLI), "--root", path],
            cwd=str(ROOT), capture_output=True, text=True,
            timeout=15,
        )
        self.assertFalse(result.stderr, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 1,
                         "CLI must emit exactly one machine-readable JSON line")
        parsed = json.loads(result.stdout)
        self.assertEqual(parsed["read_only"], True)
        self.assertEqual(parsed["decision"], "NO_GO")
        self.assertIs(parsed["may_build"], False)
        self.assertIs(parsed["may_install"], False)
        self.assertIs(parsed["may_distribute"], False)
        self.assertEqual(result.returncode, 2)
        return parsed

    def test_synthetic_clean_source_reports_unknown_signature_and_open_gates(self):
        report = self.invoke()
        checks = report["checks"]
        self.assertEqual(checks["source_git"]["state"], "PASS")
        self.assertEqual(checks["version_triad"]["state"], "PASS")
        self.assertEqual(checks["webview2_offline_file"]["state"], "PASS")
        self.assertEqual(checks["builder_sources"]["state"], "PASS")
        self.assertEqual(checks["artifact_collisions"]["state"], "PASS")
        self.assertEqual(checks["webview2_authenticode"]["state"], "UNKNOWN")
        self.assertEqual(checks["webview2_full_offline_identity"]["state"], "UNKNOWN")
        self.assertEqual(checks["installed_toolchain"]["state"], "UNKNOWN")
        self.assertEqual(checks["acceptance_ac_g"]["state"], "BLOCKED")
        self.assertEqual(checks["acceptance_ac_g"]["open_count"], 40)
        self.assertEqual(checks["acceptance_ac_g"]["missing"], [])

    def test_missing_offline_prerequisite_is_no_go_even_when_source_clean(self):
        (self.root / PREREQ).unlink()
        report = self.invoke()
        self.assertEqual(report["checks"]["source_git"]["state"], "PASS")
        self.assertEqual(report["checks"]["webview2_offline_file"]["state"], "BLOCKED")
        self.assertFalse(report["checks"]["webview2_offline_file"]["present"])

    def test_dirty_source_is_no_go_even_with_full_prerequisite_path(self):
        write(self.root, "untracked-e0-e7-change.py", "no committed evidence\n")
        report = self.invoke()
        self.assertEqual(report["checks"]["source_git"]["state"], "BLOCKED")
        self.assertTrue(report["checks"]["source_git"]["dirty_or_untracked"])

    def test_package_lock_and_updater_version_mismatch_fail_closed(self):
        for filename, data in (
            ("package.json", {"version": "1.0.24"}),
            ("package-lock.json", {"version": "1.0.22", "packages": {
                "": {"version": "1.0.23"}}}),
            ("madar_update.py", "CURRENT_VERSION = '1.0.22'\n"),
            ("scripts/build_integrated_v123.py", "builder.VERSION = '1.0.22'\n"),
        ):
            with self.subTest(file=filename):
                target = self.root / filename
                original = target.read_bytes()
                try:
                    if isinstance(data, str):
                        target.write_text(data, encoding="utf-8")
                    else:
                        if filename == "package.json":
                            full = json.loads(original)
                            full.update(data)
                            data = full
                        target.write_text(json.dumps(data), encoding="utf-8")
                    self.assertEqual(self.invoke()["checks"]["version_triad"]["state"],
                                     "BLOCKED")
                finally:
                    target.write_bytes(original)

    def test_existing_dist_is_never_trusted_as_successful_package(self):
        write(self.root, "dist/index.html", "<html>stale</html>")
        report = self.invoke()
        self.assertEqual(report["checks"]["dist"]["state"], "UNKNOWN")
        self.assertTrue(report["checks"]["dist"]["present"])
        self.assertIn("dist", report["blockers"])

    def test_missing_duplicate_and_falsely_closed_acceptance_fail_closed(self):
        matrix = self.root / "docs/modernization/MTR_E7_ACCEPTANCE_GATES_20261109.md"
        original = matrix.read_text(encoding="utf-8")
        try:
            for transform, key in (
                (lambda s: s.replace("| AC-01 | synthetic | OPEN |\n", ""), "missing"),
                (lambda s: s + "| G-01 | synthetic | OPEN |\n", "duplicates"),
                (lambda s: s.replace("| AC-02 | synthetic | OPEN |",
                                     "| AC-02 | synthetic | PASSED |"),
                 "non_open_or_unrecognized"),
            ):
                matrix.write_text(transform(original), encoding="utf-8")
                check = self.invoke()["checks"]["acceptance_ac_g"]
                self.assertEqual(check["state"], "UNKNOWN")
                self.assertTrue(check[key])
        finally:
            matrix.write_text(original, encoding="utf-8")
        matrix.unlink()
        self.assertEqual(self.invoke()["checks"]["acceptance_ac_g"]["state"],
                         "UNKNOWN")

    def test_collision_and_missing_builder_sources_are_blockers(self):
        write(self.root, "release/Madar-Desk-1.0.23-Setup.exe", b"synthetic-only")
        self.assertEqual(self.invoke()["checks"]["artifact_collisions"]["state"],
                         "BLOCKED")
        (self.root / "release/Madar-Desk-1.0.23-Setup.exe").unlink()
        (self.root / "scripts/build_p0_release_candidate.py").unlink()
        self.assertEqual(self.invoke()["checks"]["builder_sources"]["state"],
                         "BLOCKED")

    def test_relative_or_unowned_root_rejected_without_inspecting_source(self):
        report = self.invoke(Path("relative/fixture"))
        self.assertIn("unsafe_or_unavailable_root", report["blockers"])
        (self.root / MARKER).unlink()
        self.assertEqual(self.invoke()["checks"]["root"]["state"], "BLOCKED")

    def test_symlink_to_outside_root_must_fail_closed_when_platform_allows_it(self):
        outside = tempfile.TemporaryDirectory(prefix="mtr-e7-outside-")
        self.addCleanup(outside.cleanup)
        external = Path(outside.name) / "unrelated-package.json"
        external.write_text('{"version":"1.0.23"}', encoding="utf-8")
        package = self.root / "package.json"
        package.unlink()
        try:
            package.symlink_to(external)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation requires privileges on this Windows host")
        check = self.invoke()["checks"]["version_triad"]
        self.assertEqual(check["state"], "UNKNOWN")
        self.assertFalse(self.invoke()["may_build"])

    def test_git_metadata_link_out_of_synthetic_root_is_rejected(self):
        outside = tempfile.TemporaryDirectory(prefix="mtr-e7-external-git-")
        self.addCleanup(outside.cleanup)
        linked_fixture = self.root / "nested-fixture"
        linked_fixture.mkdir()
        write(linked_fixture, MARKER, json.dumps(
            {"owner": "mtr-release-readiness", "synthetic": True}))
        metadata = linked_fixture / ".git"
        # Do not touch existing .git: construct an independent disposable
        # synthetic root with a linked Git metadata directory.
        try:
            metadata.symlink_to(outside.name, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("directory symlink requires privileges")
        check = self.invoke(linked_fixture)["checks"]["source_git"]
        self.assertEqual(check["state"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
