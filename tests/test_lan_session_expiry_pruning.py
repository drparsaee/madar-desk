"""Disposable LAN session-retention regression (no operational credentials)."""

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from lan import LanService


class _SyntheticBridge:
    def __init__(self):
        self._lock = threading.RLock()

    def getState(self):
        return {"projects": [], "tasks": []}


class LanSessionExpiryPruningTests(unittest.TestCase):
    def test_new_successful_login_retires_expired_sessions_without_revoking_live(self):
        with tempfile.TemporaryDirectory(prefix="madar-lan-sessions-") as root:
            service = LanService(_SyntheticBridge(), Path(root) / "users.json")
            service.setup_owner("admin", "synthetic-password")
            with patch("lan.time.time", return_value=1000.0):
                old_token = service.authenticate("admin", "synthetic-password")["token"]
            with patch("lan.time.time", return_value=1000.0 + 12 * 3600 - 1):
                live_token = service.authenticate("admin", "synthetic-password")["token"]
            with patch("lan.time.time", return_value=1000.0 + 12 * 3600 + 1):
                with self.assertRaises(PermissionError):
                    service.authenticate("admin", "synthetic-wrong-password")
                self.assertIn(old_token, service.sessions)
                new_token = service.authenticate("admin", "synthetic-password")["token"]
                self.assertNotIn(old_token, service.sessions)
                self.assertIn(live_token, service.sessions)
                self.assertEqual(service.account_for(live_token)["username"], "admin")
                self.assertEqual(service.account_for(new_token)["username"], "admin")


if __name__ == "__main__":
    unittest.main()
