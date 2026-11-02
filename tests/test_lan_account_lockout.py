"""Disposable LAN login throttle contract; no installed host or real users."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lan import LanService, make_account


class LanAccountLockoutTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="madar-lockout-")
        users = Path(self.scratch.name) / "synthetic-users.json"
        self.service = LanService(object(), users, bind="127.0.0.1", port=0)
        self.service.setup_owner("admin", "synthetic-admin-password")
        self.service.users["viewer"] = make_account(
            "viewer", "synthetic-viewer-password", "viewer")

    def tearDown(self):
        self.scratch.cleanup()

    def test_other_account_success_cannot_reset_target_lockout(self):
        ip = "192.0.2.10"  # RFC 5737 documentation-only address
        with patch("lan.time.time", return_value=1000.0):
            for _ in range(5):
                with self.assertRaises(PermissionError):
                    self.service.authenticate("admin", "bad-password", ip)
            viewer = self.service.authenticate(
                "viewer", "synthetic-viewer-password", ip)
            self.assertEqual(self.service.account_for(viewer["token"])["role"], "viewer")
            with self.assertRaises(PermissionError):
                self.service.authenticate("admin", "bad-password", ip)
            # The viewer's successful login must not unlock the targeted admin.
            with self.assertRaisesRegex(PermissionError, "دو دقیقه"):
                self.service.authenticate("admin", "synthetic-admin-password", ip)
            # Existing authorized sessions are not invalidated by login throttling.
            self.assertEqual(self.service.account_for(viewer["token"])["role"], "viewer")
            self.assertEqual(self.service.authenticate(
                "admin", "synthetic-admin-password", "192.0.2.11"
            )["user"]["role"], "admin")

    def test_successful_target_login_before_threshold_resets_own_budget(self):
        ip = "192.0.2.12"
        with patch("lan.time.time", return_value=1000.0):
            for _ in range(5):
                with self.assertRaises(PermissionError):
                    self.service.authenticate("admin", "bad-password", ip)
            self.service.authenticate("admin", "synthetic-admin-password", ip)
            for _ in range(5):
                with self.assertRaises(PermissionError):
                    self.service.authenticate("admin", "bad-password", ip)
            self.assertEqual(self.service.authenticate(
                "admin", "synthetic-admin-password", ip
            )["user"]["role"], "admin")

    def test_locked_target_can_login_after_120_second_window(self):
        ip = "192.0.2.13"
        with patch("lan.time.time", return_value=1000.0):
            for _ in range(6):
                with self.assertRaises(PermissionError):
                    self.service.authenticate("admin", "bad-password", ip)
            with self.assertRaisesRegex(PermissionError, "دو دقیقه"):
                self.service.authenticate("admin", "synthetic-admin-password", ip)
        with patch("lan.time.time", return_value=1121.0):
            self.assertEqual(self.service.authenticate(
                "admin", "synthetic-admin-password", ip
            )["user"]["role"], "admin")

    def test_unknown_username_budget_survives_valid_other_account_login(self):
        ip = "192.0.2.14"
        with patch("lan.time.time", return_value=1000.0):
            for index in range(5):
                with self.assertRaises(PermissionError):
                    self.service.authenticate(f"nonexistent-{index}", "wrong", ip)
            viewer = self.service.authenticate(
                "viewer", "synthetic-viewer-password", ip)
            self.assertEqual(self.service.account_for(viewer["token"])["role"], "viewer")
            with self.assertRaises(PermissionError):
                self.service.authenticate("nonexistent-sixth", "wrong", ip)
            with self.assertRaisesRegex(PermissionError, "دو دقیقه"):
                self.service.authenticate("admin", "synthetic-admin-password", ip)
        with patch("lan.time.time", return_value=1121.0):
            self.assertEqual(self.service.authenticate(
                "admin", "synthetic-admin-password", ip)["user"]["role"], "admin")


if __name__ == "__main__":
    unittest.main()
