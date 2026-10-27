"""LAN directory cache must never cross Windows-client login identities."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import native_app


class ProfileCacheACLTests(unittest.TestCase):
    SERVER_ONE = "http://127.0.0.1:48210"
    SERVER_TWO = "http://127.0.0.2:48211"

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="madar-profile-acl-")
        self.root = Path(self.temporary.name)
        self.datadir_patch = patch.object(native_app, "datadir", return_value=self.root)
        self.crypto_patch = patch.object(native_app, "protect_windows",
                                         side_effect=lambda value, decrypt=False: value)
        self.datadir_patch.start()
        self.crypto_patch.start()
        self.bridge = native_app.Bridge()
        self.accounts = {
            "viewer_a": {"username": "viewer_a", "role": "viewer", "projects": ["p-sample"],
                         "displayName": "A", "avatarIcon": "user", "avatarPhoto": "",
                         "avatarColor": "#123456"},
            "viewer_b": {"username": "viewer_b", "role": "viewer", "projects": ["p-personal"],
                         "displayName": "B", "avatarIcon": "user", "avatarPhoto": "",
                         "avatarColor": "#123456"},
        }
        self.directory = {
            "viewer_a": [self.accounts["viewer_a"], {
                **self.accounts["viewer_a"], "username": "coworker_a", "displayName": "A only"}],
            "viewer_b": [self.accounts["viewer_b"], {
                **self.accounts["viewer_b"], "username": "coworker_b", "displayName": "B only"}],
        }

    def tearDown(self):
        self.crypto_patch.stop()
        self.datadir_patch.stop()
        self.temporary.cleanup()

    def server_request(self, endpoint, payload=None, login=False):
        if endpoint == "/api/login":
            return {"token": "session-" + payload["username"],
                    "user": self.accounts[payload["username"]]}
        if endpoint == "/api/state":
            return {"revision": "rev-1", "state": native_app.initial_state()}
        if endpoint == "/api/profiles":
            return {"users": self.directory[self.bridge.remote_user["username"]]}
        raise AssertionError(endpoint)

    def join(self, username, url=None):
        with patch.object(self.bridge, "_remote_request", side_effect=self.server_request):
            self.bridge.lanJoin(url or self.SERVER_ONE, username, "strong-password-test")

    def live_profiles(self):
        with patch.object(self.bridge, "_remote_request", side_effect=self.server_request):
            return self.bridge.lanProfiles()

    def offline_profiles(self):
        with patch.object(self.bridge, "_remote_request",
                          side_effect=ConnectionError("LAN unavailable")):
            return self.bridge.lanProfiles()

    def test_viewer_a_to_viewer_b_switch_cannot_reuse_directory_during_outage(self):
        self.join("viewer_a")
        self.assertEqual({p["username"] for p in self.live_profiles()},
                         {"viewer_a", "coworker_a"})
        a_cache = self.bridge.profile_cache_path.read_text(encoding="utf8")
        self.assertIn("coworker_a", a_cache)
        self.assertNotIn("password", a_cache.lower())
        self.assertNotIn("session-viewer_a", a_cache)

        self.join("viewer_b")  # Same Windows computer, different authenticated user.
        self.assertFalse(self.bridge.profile_cache_path.exists())
        self.assertEqual([p["username"] for p in self.offline_profiles()], ["viewer_b"])
        self.assertNotIn("coworker_a", json.dumps(self.offline_profiles()))
        self.assertEqual({p["username"] for p in self.live_profiles()},
                         {"viewer_b", "coworker_b"})
        self.assertEqual({p["username"] for p in self.offline_profiles()},
                         {"viewer_b", "coworker_b"})
        cache = json.loads(self.bridge.profile_cache_path.read_text(encoding="utf8"))
        self.assertEqual(cache["identity"]["username"], "viewer_b")
        self.assertEqual(cache["identity"]["role"], "viewer")
        self.assertEqual(cache["identity"]["projects"], ["p-personal"])

    def test_same_account_offline_restart_can_read_only_identity_bound_cache(self):
        self.join("viewer_b")
        self.live_profiles()
        # Startup tries to reconnect, but the LAN host is unavailable.
        with patch.object(native_app.Bridge, "_remote_request",
                          side_effect=ConnectionError("offline")):
            reopened = native_app.Bridge()
        self.assertIsNone(reopened.remote_token)
        self.assertEqual(reopened.remote_user["username"], "viewer_b")
        self.assertEqual({p["username"] for p in reopened.lanProfiles()},
                         {"viewer_b", "coworker_b"})
        reopened.client_auth_path.unlink()
        self.assertEqual(reopened.lanProfiles(), [])

    def test_valid_custom_role_survives_live_profile_sanitizing_without_leaking_fields(self):
        source = {**self.accounts["viewer_a"], "displayRole": "custom-finance",
                  "displayRoleLabel": "هماهنگ‌کننده", "displayMode": "operations",
                  "displayFeatures": ["cards", "planner"],
                  "privateSessionToken": "must-never-be-cached"}
        sanitized = native_app.Bridge._public_cached_profile(source)
        self.assertEqual(sanitized["displayRole"], "custom-finance")
        self.assertEqual(sanitized["displayRoleLabel"], "هماهنگ‌کننده")
        self.assertEqual(sanitized["displayMode"], "operations")
        self.assertEqual(sanitized["displayFeatures"], ["cards", "planner"])
        self.assertNotIn("privateSessionToken", sanitized)
        for malformed in (
            {**source, "displayFeatures": ["cards", "projectFinance"]},
            {**source, "displayFeatures": ["cards", "cards"]},
            {**source, "displayRole": "../bad"},
        ):
            with self.assertRaises(ValueError):
                native_app.Bridge._public_cached_profile(malformed)

    def test_server_change_and_role_scope_changes_reject_old_cache(self):
        self.join("viewer_a")
        self.live_profiles()
        old = self.bridge.profile_cache_path.read_bytes()

        self.join("viewer_a", self.SERVER_TWO)
        self.assertFalse(self.bridge.profile_cache_path.exists())
        # A copied old cache cannot impersonate a second host at another address.
        self.bridge.profile_cache_path.write_bytes(old)
        self.assertEqual([p["username"] for p in self.offline_profiles()], ["viewer_a"])

        self.bridge.connection["url"] = self.SERVER_ONE
        self.bridge.connection["fingerprint"] = "a" * 64
        self.assertEqual([p["username"] for p in self.offline_profiles()], ["viewer_a"])
        self.bridge.connection["fingerprint"] = ""
        # Changing privilege / scope also invalidates a previously authorized roster.
        self.bridge.remote_user = {**self.accounts["viewer_a"], "role": "viewer", "projects": []}
        self.assertEqual([p["username"] for p in self.offline_profiles()], ["viewer_a"])

    def test_legacy_bare_array_corruption_and_invalid_context_fail_closed(self):
        self.join("viewer_a")
        self.bridge.profile_cache_path.write_text(json.dumps(self.directory["viewer_b"]), encoding="utf8")
        self.assertEqual([p["username"] for p in self.offline_profiles()], ["viewer_a"])
        self.bridge.profile_cache_path.write_text("{invalid json", encoding="utf8")
        self.assertEqual([p["username"] for p in self.offline_profiles()], ["viewer_a"])
        self.bridge.remote_user = self.accounts["viewer_b"]  # mismatches protected username A
        self.assertEqual(self.offline_profiles(), [])

    def test_cache_whitelists_directory_fields_and_logout_deletes_cache(self):
        self.join("viewer_a")
        self.directory["viewer_a"][1] = {**self.directory["viewer_a"][1],
                                          "token": "secret-token-string",
                                          "password": "secret-password-string",
                                          "passwordHash": "secret-hash-string"}
        profiles = self.live_profiles()
        self.assertNotIn("token", profiles[-1])
        cached = self.bridge.profile_cache_path.read_text(encoding="utf8")
        for secret in ("secret-token-string", "secret-password-string",
                       "secret-hash-string"):
            self.assertNotIn(secret, cached)
        self.bridge.lanLeave()
        self.assertFalse(self.bridge.profile_cache_path.exists())
        self.assertFalse(self.bridge.client_auth_path.exists())
        self.assertEqual(self.bridge.lanProfiles()[0]["username"], "local")

    def test_failed_account_switch_clears_previous_cache(self):
        self.join("viewer_a")
        self.live_profiles()
        with patch.object(self.bridge, "_remote_request",
                          side_effect=ConnectionError("host not reachable")):
            with self.assertRaises(ConnectionError):
                self.bridge.lanJoin(self.SERVER_ONE, "viewer_b", "strong-password-test")
        self.assertFalse(self.bridge.profile_cache_path.exists())
        self.assertEqual(self.offline_profiles(), [])


if __name__ == "__main__":
    unittest.main()
