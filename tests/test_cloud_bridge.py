import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import native_app
from lan import revision


class CloudBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.shared = self.root / "Shared Drive"
        self.shared.mkdir()
        self.original = native_app.normalize_state(native_app.initial_state())
        self.original["projects"] = [p for p in self.original["projects"] if p["id"] == "p-sample"]
        self.original["boards"] = [b for b in self.original["boards"] if b["projectId"] == "p-sample"]
        self.identity = {"username": "member", "role": "editor", "projects": ["p-sample"]}
        self.first = self.make_client("pc1")
        self.second = self.make_client("pc2")

    def make_client(self, name):
        root = self.root / name
        root.mkdir()
        with patch.object(native_app, "datadir", return_value=root):
            client = native_app.Bridge()
        client.connection = {"mode": "client", "url": "http://192.168.1.77:48370"}
        client.remote_user = copy.deepcopy(self.identity)
        client.remote_revision = revision(self.original)
        client.offline.remember(self.original, client.remote_revision,
                                "member", client.remote_user)
        client.offline.set_sync_folder(self.shared)
        with patch.object(native_app, "protect_windows", side_effect=lambda raw, decrypt=False: raw):
            client.cloudPeerConfigure("same-paired-secret-string-between-two-windows-pcs")
        return client

    def test_two_clients_exchange_cloud_edits_during_lan_outage(self):
        def disconnected(*_args, **_kwargs):
            raise ConnectionError("LAN down")

        with patch.object(native_app, "protect_windows", side_effect=lambda raw, decrypt=False: raw):
            with patch.object(self.first, "_remote_request", side_effect=disconnected), \
                 patch.object(self.second, "_remote_request", side_effect=disconnected):
                a = self.first.getState()
                a["tasks"][0]["title"] = "edited by pc1"
                self.assertTrue(self.first.saveState(a)["offline"])
                b = self.second.getState()
                self.assertEqual(b["tasks"][0]["title"], "edited by pc1")
                b["tasks"][1]["title"] = "edited by pc2"
                self.assertTrue(self.second.saveState(b)["offline"])
                a2 = self.first.getState()
                self.assertEqual(a2["tasks"][0]["title"], "edited by pc1")
                self.assertEqual(a2["tasks"][1]["title"], "edited by pc2")
                self.assertTrue(self.first.offline.has_pending())
                self.assertTrue(self.second.offline.has_pending())
                self.assertFalse(self.first.cloudPeerStatus()["cloudVerified"])

    def test_wrong_secret_is_rejected_without_replacing_pending(self):
        def disconnected(*_args, **_kwargs):
            raise ConnectionError("LAN down")
        with patch.object(native_app, "protect_windows", side_effect=lambda raw, decrypt=False: raw):
            with patch.object(self.first, "_remote_request", side_effect=disconnected):
                a = self.first.getState()
                a["tasks"][0]["title"] = "trusted"
                self.first.saveState(a)
            self.second.cloudPeerConfigure("different-long-pairing-code-on-second-device")
            with patch.object(self.second, "_remote_request", side_effect=disconnected):
                with self.assertRaises(PermissionError):
                    self.second.getState()
            self.assertEqual(self.second.offline.get_cached()["tasks"][0]["title"],
                             self.original["tasks"][0]["title"])


if __name__ == "__main__":
    unittest.main()
