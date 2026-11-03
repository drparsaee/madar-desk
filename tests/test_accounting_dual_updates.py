"""No-network, no-install regression for both desktop update bridges."""
import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import madar_update
from standalone_accounting_desktop import AccountingDesktopAPI, JS_BRIDGE


class AccountingDualUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.api = AccountingDesktopAPI(Path(self.tmp.name) / "synthetic-book")

    def test_accounting_javascript_bridge_lists_three_release_operations(self):
        for name in ("releaseCheck", "releaseDownload", "releaseInstall"):
            self.assertIn("'" + name + "'", JS_BRIDGE)
            self.assertTrue(hasattr(self.api, name))

    def test_metadata_check_is_read_only_of_accounting_book(self):
        with patch.object(madar_update, "check", return_value={
            "available": False, "current": "1.0.12", "latest": "1.0.12"
        }) as mocked:
            self.assertFalse(self.api.releaseCheck()["available"])
            mocked.assert_called_once_with()
        self.assertFalse(self.api.path.exists())

    def test_download_does_not_use_renderer_supplied_url(self):
        official = {"available": True, "current": "1.0.12", "latest": "1.0.13",
                    "sha256": "f" * 64}
        with patch.object(madar_update, "check", return_value=official), patch.object(
            madar_update, "download", return_value={"verified": True, "path": "synthetic"}
        ) as down:
            self.assertTrue(self.api.releaseDownload()["verified"])
            down.assert_called_once_with(official)
        self.assertFalse(self.api.path.exists())

    def test_install_queues_only_after_host_guards_and_never_executes_synchronously(self):
        with patch.object(madar_update, "schedule_verified_install_after_exit",
                          return_value={"scheduledAfterExit": True, "version": "1.0.13"}) as schedule:
            self.assertTrue(self.api.releaseInstall()["scheduledAfterExit"])
            schedule.assert_called_once_with()
            self.api._exit_backed_up = True
            with self.assertRaisesRegex(RuntimeError, "closing"):
                self.api.releaseInstall()
            self.assertEqual(schedule.call_count, 1)
        self.assertFalse(self.api.path.exists())

    def test_shared_installer_revalidates_remote_source_digest_before_queue(self):
        version = {"available": True, "latest": "1.0.13", "sha256": "a" * 64}
        with patch.object(madar_update, "check", return_value=version), patch.object(
            madar_update, "download", return_value={"verified": True, "path": r"C:\QA\Madar-Setup.exe"}
        ), patch.object(madar_update.sys, "platform", "win32"), patch.object(
            madar_update.subprocess, "Popen"
        ) as spawn:
            result = madar_update.schedule_verified_install_after_exit()
            self.assertTrue(result["scheduledAfterExit"])
            command = spawn.call_args.args[0]
            self.assertEqual(command[:3], ["powershell.exe", "-NoProfile", "-NonInteractive"])
            decoded = base64.b64decode(command[4]).decode("utf-16le")
            self.assertIn("Wait-Process", decoded)
            self.assertIn("Get-FileHash", decoded)
            self.assertIn("a" * 64, decoded)
            self.assertIn("Madar-Setup.exe", decoded)

    def test_unverified_asset_cannot_start_installer(self):
        with patch.object(madar_update, "check", return_value={
            "available": True, "latest": "1.0.13", "sha256": "a" * 64
        }), patch.object(madar_update, "download", return_value={
            "verified": False, "path": "C:\\unsafe.exe"
        }), patch.object(madar_update.sys, "platform", "win32"), patch.object(
            madar_update.subprocess, "Popen"
        ) as spawn:
            with self.assertRaisesRegex(RuntimeError, "معتبر"):
                madar_update.schedule_verified_install_after_exit()
            spawn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
