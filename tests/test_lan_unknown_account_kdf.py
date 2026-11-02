"""Synthetic MD-O02 login timing-work contract, without real LAN profiles."""

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lan import LanService


class LanUnknownAccountKdfTests(unittest.TestCase):
    def test_unknown_and_existing_wrong_passwords_each_run_one_pbkdf2(self):
        with tempfile.TemporaryDirectory(prefix="madar-kdf-synthetic-") as folder:
            service = LanService(object(), Path(folder) / "users.json",
                                 bind="127.0.0.1", port=0)
            service.setup_owner("synthetic-admin", "synthetic-password-2026")
            for username, ip in (("synthetic-admin", "192.0.2.101"),
                                 ("nonexistent-user", "192.0.2.102")):
                with self.subTest(username=username):
                    with patch("lan.hashlib.pbkdf2_hmac",
                               wraps=hashlib.pbkdf2_hmac) as derive:
                        with self.assertRaisesRegex(PermissionError,
                                                    "نام کاربری یا رمز عبور نادرست است"):
                            service.authenticate(username, "incorrect", ip)
                        self.assertEqual(derive.call_count, 1)
                    self.assertNotIn("nonexistent-user", service.users)
            # Even the publicly known dummy input must never create a session.
            with self.assertRaisesRegex(PermissionError,
                                        "نام کاربری یا رمز عبور نادرست است"):
                service.authenticate("nonexistent-user", "not-a-real-madar-account",
                                     "192.0.2.103")


if __name__ == "__main__":
    unittest.main()
