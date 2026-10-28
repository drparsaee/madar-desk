"""Windows-only local issue report contract; all paths are disposable and synthetic."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "Create-Madar-Issue-Report.ps1"


@unittest.skipUnless(os.name == "nt", "Windows PowerShell script only")
class CustomerIssueReportTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="madar-report-qa-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.output = self.root / "reports"
        self.output.mkdir()
        self.appdata = self.root / "roaming"
        self.localdata = self.root / "local"
        self.appdata.mkdir()
        self.localdata.mkdir()
        self.marker = self.appdata / "MadarDesk" / "tasks.json"
        self.marker.parent.mkdir()
        self.marker.write_text("DO NOT CHANGE", encoding="utf-8")
        self.env = dict(os.environ, APPDATA=str(self.appdata), LOCALAPPDATA=str(self.localdata))

    def run_report(self, *args, output_directory=None):
        return subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", str(SCRIPT), "-AppVersion", "1.0.0-rc.15",
             "-OutputDirectory", str(output_directory or self.output), *args],
            env=self.env, cwd=self.root, capture_output=True, text=True,
            timeout=25, check=False,
        )

    def test_creates_single_local_report_without_reading_or_writing_appdata(self):
        message = ("Board failed, contact maria@example.org at 192.168.1.55 "
                   "https://support.example.org/item?id=789 and +491701234567\n"
                   "C:\\Users\\Maria\\Documents\\private.json could not open\n"
                   "Authorization: Bearer highly-secret-value\n"
                   "username=Parsa\n"
                   "شماره تماس ۰۹۱۲۳۴۵۶۷۸۹")
        proc = self.run_report("-ErrorMessage", message)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        outputs = list(self.output.glob("madar-issue-*.json"))
        self.assertEqual(len(outputs), 1)
        self.assertEqual(Path(proc.stdout.strip()).resolve(), outputs[0].resolve())
        raw = outputs[0].read_text(encoding="utf-8")
        for confidential in ("maria@example.org", "192.168.1.55", "support.example.org",
                             "+491701234567", "۰۹۱۲۳۴۵۶۷۸۹", "Maria",
                             "highly-secret-value", "Parsa",
                             "DO NOT CHANGE"):
            self.assertNotIn(confidential, raw)
        report = json.loads(raw)
        self.assertEqual(report["app_version"], "1.0.0-rc.15")
        self.assertEqual(report["schema_version"], 1)
        self.assertIn("powershell_version", report["runtime"])
        self.assertIn("os", report)
        self.assertIn("Board failed", report["error_description"])
        self.assertIn("[REDACTED_SENSITIVE_LINE]", report["error_description"])
        self.assertEqual(self.marker.read_text(encoding="utf-8"), "DO NOT CHANGE")
        self.assertEqual(set(self.appdata.rglob("*")), {self.marker.parent, self.marker})
        self.assertFalse(list(self.output.glob("*.tmp")))

    def test_rejects_operational_appdata_folder_as_report_destination(self):
        proc = self.run_report("-ErrorMessage", "Cannot see board",
                               output_directory=self.marker.parent)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("protected", proc.stderr.lower())
        self.assertFalse(list(self.marker.parent.glob("madar-issue-*.json")))
        self.assertEqual(self.marker.read_text(encoding="utf-8"), "DO NOT CHANGE")

    def test_empty_message_and_missing_output_folder_create_nothing(self):
        empty = self.run_report("-ErrorMessage", "   ")
        self.assertNotEqual(empty.returncode, 0)
        self.assertFalse(list(self.output.iterdir()))
        missing = self.run_report("-ErrorMessage", "Unexpected error",
                                  output_directory=self.root / "missing")
        self.assertNotEqual(missing.returncode, 0)
        self.assertFalse((self.root / "missing").exists())
        self.assertFalse(list(self.output.iterdir()))

    def test_rejects_known_cloud_sync_destination(self):
        cloud = self.root / "OneDrive" / "reports"
        cloud.mkdir(parents=True)
        proc = self.run_report("-ErrorMessage", "Board failed",
                               output_directory=cloud)
        self.assertNotEqual(proc.returncode, 0)
        self.assertFalse(list(cloud.iterdir()))


if __name__ == "__main__":
    unittest.main()
