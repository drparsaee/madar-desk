"""Synthetic LAN registry publication failure during account deletion."""

from copy import deepcopy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lan import LanService
from tests.test_lan_delete_registry_failure import _SyntheticBridge


class DeletePartialRegistrySaveTests(unittest.TestCase):
    def test_committed_registry_then_error_restores_both_files_and_session(self):
        with tempfile.TemporaryDirectory(prefix="madar-registry-partial-") as directory:
            bridge = _SyntheticBridge(Path(directory) / "state.json")
            users_path = Path(directory) / "users.json"
            service = LanService(bridge, users_path)
            service.setup_owner("admin", "synthetic-admin-password")
            admin = service.authenticate("admin", "synthetic-admin-password")["token"]
            service.upsert_user(admin, {"username": "editor", "password": "synthetic-editor-password", "role": "editor"})
            editor = service.authenticate("editor", "synthetic-editor-password")["token"]
            old_state = deepcopy(bridge.state)
            old_registry = json.loads(users_path.read_text(encoding="utf8"))
            original_store = service._store_users
            calls = 0

            def commit_then_raise(users):
                nonlocal calls
                calls += 1
                result = original_store(users)
                if calls == 1:
                    raise OSError("synthetic registry post-commit failure")
                return result

            with patch.object(service, "_store_users", side_effect=commit_then_raise):
                with self.assertRaisesRegex(OSError, "synthetic registry post-commit failure"):
                    service.delete_user(admin, "editor")

            self.assertEqual(calls, 2)
            self.assertEqual(json.loads(users_path.read_text(encoding="utf8")), old_registry)
            self.assertEqual(json.loads(bridge.state_path.read_text(encoding="utf8")), old_state)
            self.assertEqual(service.account_for(editor)["username"], "editor")
            self.assertIn("editor", LanService(bridge, users_path).users)

    def test_foreign_registry_revision_is_never_overwritten(self):
        with tempfile.TemporaryDirectory(prefix="madar-registry-partial-") as directory:
            bridge = _SyntheticBridge(Path(directory) / "state.json")
            users_path = Path(directory) / "users.json"
            service = LanService(bridge, users_path)
            service.setup_owner("admin", "synthetic-admin-password")
            admin = service.authenticate("admin", "synthetic-admin-password")["token"]
            service.upsert_user(admin, {"username": "editor", "password": "synthetic-editor-password", "role": "editor"})
            original_store = service._store_users

            def foreign_then_raise(users):
                original_store({**users, "foreign-synthetic": {"marker": "external"}})
                raise OSError("synthetic foreign registry revision")

            with patch.object(service, "_store_users", side_effect=foreign_then_raise):
                with self.assertRaisesRegex(RuntimeError, "unexpected registry revision"):
                    service.delete_user(admin, "editor")

            self.assertIn("foreign-synthetic", json.loads(users_path.read_text(encoding="utf8")))

    def test_failed_registry_compensation_reports_explicit_error(self):
        with tempfile.TemporaryDirectory(prefix="madar-registry-partial-") as directory:
            bridge = _SyntheticBridge(Path(directory) / "state.json")
            users_path = Path(directory) / "users.json"
            service = LanService(bridge, users_path)
            service.setup_owner("admin", "synthetic-admin-password")
            admin = service.authenticate("admin", "synthetic-admin-password")["token"]
            service.upsert_user(admin, {"username": "editor", "password": "synthetic-editor-password", "role": "editor"})
            original_store = service._store_users
            calls = 0

            def fail_registry_rollback(users):
                nonlocal calls
                calls += 1
                if calls == 1:
                    original_store(users)
                    raise OSError("synthetic post-commit failure")
                raise OSError("synthetic registry rollback failure")

            with patch.object(service, "_store_users", side_effect=fail_registry_rollback):
                with self.assertRaisesRegex(RuntimeError, "user-registry rollback failed"):
                    service.delete_user(admin, "editor")
            self.assertEqual(calls, 2)
            self.assertNotIn("editor", json.loads(users_path.read_text(encoding="utf8")))
            self.assertIn("editor", service.users)


if __name__ == "__main__":
    unittest.main()
