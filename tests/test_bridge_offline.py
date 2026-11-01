import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import native_app
from lan import revision


class BridgeOfflineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="madar-bridge-offline-")
        self.root = Path(self.tmp.name)
        self.patch = patch.object(native_app, "datadir", return_value=self.root)
        self.patch.start()
        self.bridge = native_app.Bridge()
        self.bridge.connection = {"mode": "client", "url": "http://127.0.0.1:49001"}
        self.bridge.remote_user = {"username": "member", "role": "editor", "projects": ["p-sample"]}
        self.sample = native_app.normalize_state(native_app.initial_state())
        self.sample["projects"] = [p for p in self.sample["projects"] if p["id"] == "p-sample"]
        self.sample["boards"] = [b for b in self.sample["boards"] if b["projectId"] == "p-sample"]
        self.bridge.remote_revision = revision(self.sample)
        self.bridge.offline.remember(self.sample, self.bridge.remote_revision, "member", self.bridge.remote_user)

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_client_can_edit_offline_and_reconcile_when_host_returns(self):
        with patch.object(self.bridge, "_remote_request", side_effect=ConnectionError("server off")):
            offline = self.bridge.getState()
            self.assertTrue(offline["__offline"])
            offline["tasks"][0]["title"] = "edited locally"
            result = self.bridge.saveState(offline)
            self.assertTrue(result["offline"])
            self.assertTrue(self.bridge.offline.has_pending())

        latest = json.loads(json.dumps(self.sample))
        latest["tasks"][1]["title"] = "edited on host"
        def request(endpoint, payload=None):
            nonlocal latest
            if payload is None:
                return {"state": latest, "revision": revision(latest),
                        "user": self.bridge.remote_user}
            self.assertEqual(payload["revision"], revision(latest))
            latest = payload["state"]
            return {"state": latest, "revision": revision(latest),
                    "user": self.bridge.remote_user}

        with patch.object(self.bridge, "_remote_request", side_effect=request):
            synced = self.bridge.getState()
        self.assertFalse(self.bridge.offline.has_pending())
        self.assertEqual(synced["tasks"][0]["title"], "edited locally")
        self.assertEqual(synced["tasks"][1]["title"], "edited on host")

    def test_client_does_not_discard_overlapping_edit(self):
        local = self.bridge.offline.get_cached()
        local["tasks"][0]["title"] = "edited locally"
        with patch.object(self.bridge, "_remote_request", side_effect=ConnectionError("server off")):
            self.bridge.saveState(local)
        latest = json.loads(json.dumps(self.sample))
        latest["tasks"][0]["title"] = "edited on host"
        # This mock represents an already authenticated, reachable LAN host.
        # The offline save correctly marked the network unavailable. Without
        # restoring a synthetic session, getState() attempts DPAPI credential
        # reconnection (not present in this disposable fixture) and returns
        # the offline cache without ever invoking the mocked host response.
        self.bridge.remote_token = "synthetic-authorized-session"
        self.bridge._network_available = True
        with patch.object(self.bridge, "_remote_request", return_value={
            "state": latest, "revision": revision(latest),
            "user": self.bridge.remote_user
        }):
            with self.assertRaisesRegex(RuntimeError, "CONFLICT"):
                self.bridge.getState()
        self.assertTrue(self.bridge.offline.has_pending())

    def test_offline_viewer_must_not_write(self):
        self.bridge.remote_user["role"] = "viewer"
        with self.assertRaises(PermissionError):
            self.bridge.saveState(self.sample)


if __name__ == "__main__":
    unittest.main()
