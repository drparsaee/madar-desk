"""E7 read-only source/metadata preflight. NEVER invoke installers or builders.

Every check reads committed/source files or calls Git status/rev-parse only.
No temp directory, package build, process launch, GUI, registry, profile or
network access is required. Execute with Python -B to avoid bytecode writes.
"""

import ast
import json
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts" / "build_integrated_v123.py"
BUILDER = ROOT / "scripts" / "build_p0_release_candidate.py"


def assigned_literal(path, variable):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    values = [
        node.value.value for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == variable
                for target in node.targets)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    ]
    return values


class E7PackagingPreflightReadOnly(unittest.TestCase):
    def test_version_identity_in_package_lock_and_updater(self):
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
        self.assertEqual(package["version"], "1.0.23")
        self.assertEqual(lock["version"], package["version"])
        self.assertEqual(lock["packages"][""]["version"], package["version"])
        self.assertEqual(assigned_literal(ROOT / "madar_update.py", "CURRENT_VERSION"),
                         [package["version"]])
        self.assertIn("scripts/build_integrated_v123.py",
                      package["scripts"]["dist:rc"])
        self.assertIn("--webview2 release/.madar-inno-prereq/"
                      "MicrosoftEdgeWebView2RuntimeInstallerX64.exe",
                      package["scripts"]["dist:rc"])

    def test_builder_requires_clean_source_and_is_not_a_dry_run(self):
        wrapper = WRAPPER.read_text(encoding="utf-8")
        builder = BUILDER.read_text(encoding="utf-8")
        for phrase in ("source_git_commit(builder.ROOT)",
                       "Release source has uncommitted or untracked files",
                       "builder.main()", "update-index",
                       'MANIFEST.open("x"'):
            self.assertIn(phrase, wrapper)
        for phrase in ("npm.cmd", "PyInstaller", "--noconfirm", "ISCC",
                       "RELEASE.mkdir", "QA_ROOT.mkdir", "compile_setup(qa=True",
                       "compile_setup(qa=False"):
            self.assertIn(phrase, builder)
        self.assertNotIn("--dry-run", wrapper)
        self.assertNotIn("--dry-run", builder)

    def test_installer_has_separate_real_profile_and_webview2_side_effects(self):
        iss = (ROOT / "scripts" / "madar-update.iss").read_text(encoding="utf-8")
        preflight = (ROOT / "scripts" / "Madar-Upgrade-Preflight.ps1").read_text(
            encoding="utf-8")
        activation = (ROOT / "scripts" / "Madar-Activate-Version.ps1").read_text(
            encoding="utf-8")
        for phrase in ("#ifdef QA", "Uninstallable=no", "DataRoot()",
                       "BackupRoot()", "MicrosoftEdgeWebView2RuntimeInstallerX64.exe",
                       "'/silent /install'", "Madar-Activate-Version.ps1"):
            self.assertIn(phrase, iss)
        self.assertIn("ZipFile]::CreateFromDirectory", preflight)
        self.assertIn("[IO.File]::Replace", activation)
        self.assertIn("previous-version.txt", activation)

    def test_report_current_blockers_without_mutating_workspace(self):
        status = subprocess.run(
            ["git", "--no-optional-locks", "-C", str(ROOT),
             "status", "--porcelain=v1",
             "--untracked-files=normal"],
            check=True, capture_output=True, text=True, encoding="utf-8")
        head = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--verify", "HEAD"],
            check=True, capture_output=True, text=True, encoding="utf-8")
        prereq = ROOT / "release" / ".madar-inno-prereq" / (
            "MicrosoftEdgeWebView2RuntimeInstallerX64.exe")
        outputs = (
            "Madar-Desk-v1.0.23-Cumulative-20261107-SettingsTaraz.exe",
            "Madar-Desk-1.0.23-Setup-QA.exe",
            "Madar-Desk-1.0.23-Setup.exe",
            "Madar-Desk-1.0.23-Setup.release.json",
            "Madar-Desk-1.0.23-Setup-QA.acceptance.json",
        )
        report = {
            "head": head.stdout.strip(),
            "dirty_or_untracked": bool(status.stdout.strip()),
            "webview2_offline_prereq_present": prereq.is_file(),
            "release_artifact_collision": any(
                (ROOT / "release" / name).exists() for name in outputs),
            "dist_present_not_attested": (ROOT / "dist" / "index.html").is_file(),
        }
        report["current_builder_source_gates_pass"] = (
            not report["dirty_or_untracked"]
            and report["webview2_offline_prereq_present"]
            and not report["release_artifact_collision"])
        print("E7_READ_ONLY_PREFLIGHT " + json.dumps(report, sort_keys=True))
        self.assertEqual(len(report["head"]), 40)
        self.assertEqual(report["current_builder_source_gates_pass"],
                         not (report["dirty_or_untracked"]
                              or not report["webview2_offline_prereq_present"]
                              or report["release_artifact_collision"]))
        # Even passing these partial checks would NOT assert installer safety,
        # offline compiler availability, Microsoft signature or E7 acceptance.


if __name__ == "__main__":
    unittest.main()
