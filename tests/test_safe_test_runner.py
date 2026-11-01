"""Pure/synthetic checks for the safe default npm test entry point."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

from tools.safe_test_runner import isolated_environment, node_totals, run_logged_phase


class SafeTestRunnerTests(unittest.TestCase):
    def test_profile_and_sensitive_overrides_are_isolated(self):
        with tempfile.TemporaryDirectory(prefix="madar-safe-runner-unit-") as directory:
            root = Path(directory) / "profile"
            env = isolated_environment(root, {
                "APPDATA": "C:\\Real-User\\Roaming",
                "LOCALAPPDATA": "C:\\Real-User\\Local",
                "USERPROFILE": "C:\\Real-User",
                "HOME": "C:\\Real-User",
                "MADAR_FINANCE_DB": "C:\\Real-User\\accounting.sqlite",
                "PARSIAN_BACKUP": "D:\\PARSIAN.BAK",
                "VITE_SECRET": "must-not-reach-build",
                "NODE_OPTIONS": "--require C:\\Real-User\\inject.js",
                "PATH": os.environ.get("PATH", ""),
            })
            for key in ("APPDATA", "LOCALAPPDATA", "USERPROFILE", "HOME",
                        "TEMP", "TMP", "TMPDIR", "XDG_DATA_HOME"):
                self.assertTrue(Path(env[key]).is_relative_to(root), key)
                self.assertTrue(Path(env[key]).is_dir(), key)
            for key in ("MADAR_FINANCE_DB", "PARSIAN_BACKUP", "VITE_SECRET",
                        "NODE_OPTIONS"):
                self.assertNotIn(key, env)
            self.assertEqual(env["PYTHONDONTWRITEBYTECODE"], "1")

    def test_subprocess_observes_only_synthetic_profile(self):
        with tempfile.TemporaryDirectory(prefix="madar-safe-runner-unit-") as directory:
            scratch = Path(directory)
            env = isolated_environment(scratch / "profile")
            printed = run_logged_phase(
                "profile-probe", [sys.executable, "-B", "-c",
                    "import os;print(os.environ['APPDATA'])"], env, scratch, timeout=10)
            self.assertIn(str(scratch / "profile" / "Roaming"), printed)
            self.assertNotIn("C:\\Real-User", printed)

    def test_chrome_compatibility_keeps_only_windows_profile_identity(self):
        with tempfile.TemporaryDirectory(prefix="madar-safe-runner-unit-") as directory:
            root = Path(directory) / "browser"
            source = dict(os.environ, MADAR_FINANCE_DB="D:\\financial.sqlite")
            env = isolated_environment(root, source, browser_compatible=True)
            for key in ("APPDATA", "LOCALAPPDATA", "TEMP", "HOME"):
                self.assertTrue(Path(env[key]).is_relative_to(root), key)
            self.assertNotIn("MADAR_FINANCE_DB", env)
            if os.name == "nt":
                self.assertEqual(env["USERPROFILE"], os.environ["USERPROFILE"])
            else:
                self.assertTrue(Path(env["USERPROFILE"]).is_relative_to(root))

    def test_node_reporter_totals_include_skips(self):
        output = "\n".join(("ℹ tests 530", "ℹ pass 530", "ℹ fail 0", "ℹ skipped 0"))
        self.assertEqual(node_totals(output), {
            "tests": 530, "pass": 530, "fail": 0, "skipped": 0})
        for unsafe in (
            output.replace("skipped 0", "skipped 1"),
            output.replace("pass 530", "pass 529"),
            output.replace("fail 0", "fail 1"),
            "✔ one test passed, but no totals",
        ):
            with self.subTest(unsafe=unsafe):
                with self.assertRaises(RuntimeError):
                    node_totals(unsafe)

    def test_package_test_script_calls_sandbox_launcher(self):
        package = json.loads((Path(__file__).parents[1] / "package.json").read_text(
            encoding="utf-8"))
        self.assertEqual(package["scripts"]["test"],
                         "python -B tools/safe_test_runner.py")


if __name__ == "__main__":
    unittest.main()
