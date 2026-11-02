"""Synthetic first-owner setup failure and publication parity checks."""

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from lan import LanService


class _Bridge:
    def __init__(self):
        self._lock = threading.RLock()

    def getState(self):
        return {"projects": [], "tasks": []}


class FirstOwnerPublicationTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="madar-first-owner-")
        self.addCleanup(self.scratch.cleanup)
        self.path = Path(self.scratch.name) / "users.json"
        self.service = LanService(_Bridge(), self.path)

    def test_postpublication_error_does_not_install_unconfirmed_owner(self):
        real_store = self.service._store_users
        calls = []

        def publish_then_raise(users):
            calls.append(1)
            real_store(users)
            if len(calls) == 1:
                raise OSError("synthetic postpublication failure")

        with patch.object(self.service, "_store_users", side_effect=publish_then_raise):
            with self.assertRaises(OSError):
                self.service.setup_owner("owner", "synthetic-owner-password")
        self.assertEqual(self.service.users, {})
        self.assertFalse(self.path.exists(), "failed first setup must not leave an owner registry")
        self.assertEqual(LanService(_Bridge(), self.path).users, {})
        self.assertGreaterEqual(len(calls), 1)

    def test_prepublication_error_keeps_first_setup_uninitialized(self):
        with patch.object(self.service, "_store_users", side_effect=OSError("synthetic no write")):
            with self.assertRaises(OSError):
                self.service.setup_owner("owner", "synthetic-owner-password")
        self.assertFalse(self.path.exists())
        self.assertEqual(self.service.users, {})

    def test_unexpected_registry_revision_is_not_deleted(self):
        real_store = self.service._store_users

        def foreign_then_raise(_candidate):
            real_store({"foreign": {"sentinel": "synthetic external writer"}})
            raise OSError("synthetic external write")

        with patch.object(self.service, "_store_users", side_effect=foreign_then_raise):
            with self.assertRaisesRegex(RuntimeError, "unexpected registry revision"):
                self.service.setup_owner("owner", "synthetic-owner-password")
        self.assertIn("foreign", self.path.read_text(encoding="utf8"))
        self.assertEqual(self.service.users, {})

    def test_successful_first_setup_is_durable_and_cannot_be_repeated(self):
        self.service.setup_owner("owner", "synthetic-owner-password")
        self.assertIn("owner", LanService(_Bridge(), self.path).users)
        with self.assertRaises(ValueError):
            self.service.setup_owner("other", "synthetic-other-password")


if __name__ == "__main__":
    unittest.main()
