"""V1 LAN acceptance: TWO simultaneous loopback hosts and disposable profiles.

This is an in-process test of real listening HTTP(S) sockets and desktop Bridges.
It does not simulate two separate physical Windows machines or network equipment.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import os
from pathlib import Path
import ssl
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import native_app
from lan import LanService, certificate_fingerprint, pinned_https_json
try:
    # unittest discover -s tests: tests directory is directly on sys.path.
    from test_lan_tls import _CERT, _KEY
except ModuleNotFoundError:
    # python -m unittest tests.test_lan_v1_acceptance: qualified import path.
    from tests.test_lan_tls import _CERT, _KEY


PASSWORD = "v1-testing-password"


class TwoHostLanV1Acceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="madar-v1-lan-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {"APPDATA": str(self.root / "appdata")})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.host_a = self.make_bridge("host-a")
        self.host_b = self.make_bridge("host-b")
        # Only acceptance fixtures get demo projects; never seed customer data.
        self.host_a.saveState(native_app.initial_state())
        self.host_b.saveState(native_app.initial_state())
        self.cert = self.root / "localhost-test.crt"
        self.key = self.root / "localhost-test.key"
        self.cert.write_text(_CERT, encoding="ascii")
        self.key.write_text(_KEY, encoding="ascii")
        self.a = LanService(self.host_a, self.root / "host-a" / "users.json",
                            bind="127.0.0.1", port=0)
        self.b = LanService(self.host_b, self.root / "host-b" / "users.json",
                            bind="127.0.0.1", port=0,
                            certfile=self.cert, keyfile=self.key)
        self.a.setup_owner("owner-a", PASSWORD)
        self.b.setup_owner("owner-b", PASSWORD)
        self.a_base = f"http://127.0.0.1:{self.a.start()}"
        self.b_base = f"https://127.0.0.1:{self.b.start()}"
        self.pin = certificate_fingerprint(self.cert)
        # Cleanups intentionally reverse registration order and stop listeners
        # before removing any temporary files, even on assertion failures.
        self.addCleanup(self.b.stop)
        self.addCleanup(self.a.stop)
        self.owner_a = self.login(self.a_base, "owner-a")
        self.owner_b = self.login(self.b_base, "owner-b")

    def make_bridge(self, folder):
        root = self.root / folder
        root.mkdir(parents=True, exist_ok=True)
        with patch.object(native_app, "datadir", return_value=root):
            return native_app.Bridge()

    def call(self, base, endpoint, body=None, token=None, *, method=None,
             content_type="application/json", raw=False, headers=None):
        request_headers = {"Content-Type": content_type, **(headers or {})}
        if token is not None:
            request_headers["Authorization"] = "Bearer " + token
        data = None if body is None else (body if raw else json.dumps(body, ensure_ascii=False).encode("utf8"))
        actual_method = method or ("POST" if body is not None else "GET")
        url = base + endpoint
        if base.startswith("https://"):
            return pinned_https_json(url, self.pin, method=actual_method,
                                     data=data, headers=request_headers, timeout=5)
        with urlopen(Request(url, data=data, headers=request_headers,
                             method=actual_method), timeout=5) as response:
            return json.loads(response.read().decode("utf8"))

    def login(self, base, username, password=PASSWORD):
        return self.call(base, "/api/login", {"username": username, "password": password})["token"]

    def create(self, username, role, projects=None, *, host=None):
        base = host or self.a_base
        owner = self.owner_b if base == self.b_base else self.owner_a
        self.call(base, "/api/user", {
            "username": username, "password": PASSWORD,
            "role": role, "projects": projects}, owner)
        return self.login(base, username)

    def require_status(self, code, work):
        with self.assertRaises(HTTPError) as raised:
            work()
        self.assertEqual(raised.exception.code, code)
        payload = json.loads(raised.exception.read().decode("utf8"))
        self.assertIsInstance(payload.get("error"), str)

    def test_two_live_hosts_are_isolated_and_scope_is_enforced(self):
        editor = self.create("sample-editor", "editor", ["p-sample"])
        viewer = self.create("private-viewer", "viewer", ["p-personal"])
        self.create("other-host-user", "editor", None, host=self.b_base)
        a_state = self.call(self.a_base, "/api/state", token=editor)
        v_state = self.call(self.a_base, "/api/state", token=viewer)
        b_state = self.call(self.b_base, "/api/state", token=self.owner_b)
        self.assertEqual([p["id"] for p in a_state["state"]["projects"]], ["p-sample"])
        self.assertEqual([p["id"] for p in v_state["state"]["projects"]], ["p-personal"])
        self.assertFalse(v_state["state"]["tasks"])
        self.assertEqual(len(b_state["state"]["projects"]), 2)
        self.require_status(403, lambda: self.call(self.b_base, "/api/state", token=editor))
        self.require_status(403, lambda: self.call(self.a_base, "/api/state", token=self.owner_b))
        self.require_status(403, lambda: self.call(self.a_base, "/api/users", token=editor))
        self.require_status(403, lambda: self.call(self.a_base, "/api/state", {
            "state": v_state["state"], "revision": v_state["revision"]}, viewer))
        self.require_status(403, lambda: self.call(self.a_base, "/api/user", {
            "username": "evil-user", "password": PASSWORD, "role": "admin"}, editor))
        self.assertNotIn("evil-user", self.a.users)
        # One host's committed changes cannot silently appear on the other host.
        update = deepcopy(a_state["state"])
        update["tasks"][0]["title"] = "ویرایش محدود میزبان A"
        self.call(self.a_base, "/api/state", {
            "state": update, "revision": a_state["revision"]}, editor)
        self.assertNotEqual(self.host_a.getState()["tasks"][0]["title"],
                            self.host_b.getState()["tasks"][0]["title"])

    def test_bad_credentials_and_malformed_contract_fail_with_json_errors(self):
        self.require_status(403, lambda: self.call(self.a_base, "/api/state"))
        self.require_status(403, lambda: self.call(self.a_base, "/api/login", {
            "username": "owner-a", "password": "incorrect-password"}))
        # Malformed username must be a controlled 400, never a broken connection.
        self.require_status(400, lambda: self.call(self.a_base, "/api/login", {
            "username": ["owner-a"], "password": PASSWORD}))
        self.require_status(400, lambda: self.call(self.a_base, "/api/login", {
            "username": {"fake": "owner-a"}, "password": PASSWORD}))
        self.require_status(400, lambda: self.call(self.a_base, "/api/login", {
            "username": "owner-a", "password": ["bad"]}))
        self.require_status(400, lambda: self.call(self.a_base, "/api/profile", b"{not json",
                                               self.owner_a, raw=True))
        self.require_status(415, lambda: self.call(self.a_base, "/api/user", {"x": 1},
                                                   self.owner_a, content_type="text/plain"))
        self.require_status(405, lambda: self.call(self.a_base, "/api/login"))
        self.require_status(404, lambda: self.call(self.a_base, "/users.json"))
        self.require_status(404, lambda: self.call(self.a_base, "/api/unknown"))
        self.require_status(403, lambda: self.call(self.a_base, "/api/finance-overview",
                                                   token=self.create("viewer2", "viewer")))
        self.assertNotIn("passwordHash", self.call(self.a_base, "/api/users",
                                                   token=self.owner_a)["users"][0])

    def test_wrong_content_type_consumes_body_and_returns_reliable_415(self):
        # A response that leaves request bytes unread can become WinError
        # 10053 on Windows, masking an intended JSON 415 with a TCP reset.
        for attempt in range(24):
            self.require_status(415, lambda: self.call(
                self.a_base, "/api/user", {"x": "q" * (256 + attempt * 31)},
                self.owner_a, content_type="text/plain"))
        self.assertEqual(len(self.a.users), 1)

    def test_login_throttling_blocks_repeated_guesses_but_keeps_existing_session(self):
        for _ in range(6):
            self.require_status(403, lambda: self.call(self.a_base, "/api/login", {
                "username": "owner-a", "password": "wrong"}))
        self.require_status(403, lambda: self.call(self.a_base, "/api/login", {
            "username": "owner-a", "password": PASSWORD}))
        self.assertEqual(len(self.call(self.a_base, "/api/state",
                                       token=self.owner_a)["state"]["projects"]), 2)
        # Throttling on host A must not impact the separately running host B.
        self.assertTrue(self.call(self.b_base, "/api/state",
                                  token=self.owner_b)["revision"])

    def test_parallel_writes_with_identical_revision_have_one_winner(self):
        editor = self.create("writer", "editor", ["p-sample"])
        initial = self.call(self.a_base, "/api/state", token=editor)
        def save(title):
            edited = deepcopy(initial["state"])
            edited["tasks"][0]["title"] = title
            try:
                self.call(self.a_base, "/api/state", {
                    "state": edited, "revision": initial["revision"]}, editor)
                return 200
            except HTTPError as exc:
                return exc.code
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(save, ["هم‌زمان اول", "هم‌زمان دوم"]))
        self.assertEqual(sorted(outcomes), [200, 409])
        winner = self.host_a.getState()["tasks"][0]["title"]
        self.assertIn(winner, ["هم‌زمان اول", "هم‌زمان دوم"])
        self.require_status(409, lambda: self.call(self.a_base, "/api/state", {
            "state": initial["state"], "revision": initial["revision"]}, editor))

    def test_concurrent_admin_role_change_and_save_have_no_deadlock(self):
        editor = self.create("concurrent", "editor", ["p-sample"])
        current = self.call(self.a_base, "/api/state", token=editor)
        changed = deepcopy(current["state"])
        changed["tasks"][0]["title"] = "race-commit"
        def save():
            try:
                self.call(self.a_base, "/api/state", {
                    "state": changed, "revision": current["revision"]}, editor)
                return 200
            except HTTPError as exc:
                return exc.code
        def downgrade():
            self.call(self.a_base, "/api/user", {
                "username": "concurrent", "role": "viewer",
                "projects": ["p-sample"], "password": ""}, self.owner_a)
            return 200
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(save), executor.submit(downgrade)]
            outcomes = [future.result(timeout=7) for future in futures]
        self.assertIn(outcomes[0], (200, 403, 409))
        self.assertEqual(outcomes[1], 200)
        self.assertEqual(self.a.users["concurrent"]["role"], "viewer")
        now = self.call(self.a_base, "/api/state", token=editor)
        self.require_status(403, lambda: self.call(self.a_base, "/api/state", {
            "state": now["state"], "revision": now["revision"]}, editor))

    def test_offline_same_card_conflict_keeps_remote_change(self):
        editor = self.create("offline-editor", "editor", ["p-sample"])
        client = self.make_bridge("client-offline")
        client.lanJoin(self.a_base, "offline-editor", PASSWORD)
        initial = client.getState()
        modified = deepcopy(initial)
        modified["tasks"][0]["title"] = "edited offline"
        self.a.stop()  # Real closed server socket, not mocked network response.
        saved = client.saveState(modified)
        self.assertTrue(saved["offline"])
        self.assertTrue(client.offline.has_pending())
        host_updated = self.host_a.getState()
        host_updated["tasks"][0]["title"] = "edited by host while offline"
        self.host_a.saveState(host_updated)
        self.a.start()  # Same port/server identity, after offline edit has queued.
        with self.assertRaisesRegex(RuntimeError, "CONFLICT"):
            client.getState()
        self.assertEqual(self.host_a.getState()["tasks"][0]["title"],
                         "edited by host while offline")
        self.assertTrue(client.offline.has_pending())
        self.assertNotEqual(self.host_a.getState()["tasks"][0]["title"],
                            self.host_b.getState()["tasks"][0]["title"])

    def test_offline_nonoverlapping_edits_reconcile_without_overwriting_host(self):
        self.create("offline-merge", "editor", ["p-sample"])
        client = self.make_bridge("client-nonoverlap")
        client.lanJoin(self.a_base, "offline-merge", PASSWORD)
        initial = client.getState()
        self.assertGreaterEqual(len(initial["tasks"]), 2)
        modified = deepcopy(initial)
        modified["tasks"][0]["title"] = "offline first card"
        self.a.stop()
        self.assertTrue(client.saveState(modified)["offline"])
        host_updated = self.host_a.getState()
        changed_id = initial["tasks"][1]["id"]
        for task in host_updated["tasks"]:
            if task["id"] == changed_id:
                task["title"] = "host second card"
        self.host_a.saveState(host_updated)
        self.a.start()
        reconciled = client.getState()
        by_id = {t["id"]: t["title"] for t in reconciled["tasks"]}
        self.assertEqual(by_id[initial["tasks"][0]["id"]], "offline first card")
        self.assertEqual(by_id[changed_id], "host second card")
        self.assertFalse(client.offline.has_pending())

    def test_https_fingerprint_prevents_login_transmission_on_mismatch(self):
        before = set(self.b.sessions)
        correct = pinned_https_json(self.b_base + "/api/state", self.pin,
                                    headers={"Authorization": "Bearer " + self.owner_b})
        self.assertEqual(len(correct["state"]["projects"]), 2)
        colon_pin = ":".join(self.pin[i:i+2] for i in range(0, 64, 2))
        self.assertEqual(pinned_https_json(self.b_base + "/api/state", colon_pin,
                          headers={"Authorization": "Bearer " + self.owner_b})["revision"],
                         correct["revision"])
        with self.assertRaises(ssl.SSLCertVerificationError):
            pinned_https_json(self.b_base + "/api/login", "0" * 64, method="POST",
                              data={"username": "owner-b", "password": PASSWORD})
        self.assertEqual(before, set(self.b.sessions))
        self.require_status(403, lambda: self.call(self.b_base, "/api/state",
                                                  token=self.owner_a))
        with self.assertRaises(ValueError):
            pinned_https_json(self.a_base + "/api/login", self.pin,
                              method="POST", data={"username": "owner-a",
                                                   "password": PASSWORD})


if __name__ == "__main__":
    unittest.main()
