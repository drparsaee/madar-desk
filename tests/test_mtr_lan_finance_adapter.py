"""Synthetic pinned-TLS MadarHost finance-intent pilot; never contacts Taraz."""
import hashlib
from http.client import HTTPSConnection
import json
from pathlib import Path
import ssl
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import native_app
from lan import LanService, certificate_fingerprint, pinned_https_json
from mtr_host_request_store import HostRequestStore
from tests.test_lan_tls import _CERT, _KEY


PASSWORD = "synthetic-host-password-32-chars"
CARD = "example-2"


class MtrLanFinancePilotTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mtr-lan-pilot-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        with patch.object(native_app, "datadir", return_value=self.root):
            self.bridge = native_app.Bridge()
            self.bridge.saveState(native_app.initial_state())
        cert = self.root / "synthetic.crt"
        key = self.root / "synthetic.key"
        cert.write_text(_CERT, encoding="ascii")
        key.write_text(_KEY, encoding="ascii")
        self.service = LanService(
            self.bridge, self.root / "users.json", bind="127.0.0.1", port=0,
            certfile=cert, keyfile=key,
        )
        self.service.setup_owner("owner", PASSWORD)
        self.port = self.service.start()
        self.addCleanup(self.service.stop)
        self.url = f"https://127.0.0.1:{self.port}"
        self.pin = certificate_fingerprint(cert)
        self.owner_token = self.service.authenticate("owner", PASSWORD)["token"]
        for name, role, projects, finance_edit in (
            ("writer", "editor", ["p-sample"], True),
            ("outsider", "editor", ["p-personal"], True),
            ("observer", "viewer", ["p-sample"], False),
        ):
            self.service.upsert_user(self.owner_token, {
                "username": name, "role": role, "projects": projects,
                "password": PASSWORD, "financeEdit": finance_edit,
            })
        self.tokens = {name: self.service.authenticate(name, PASSWORD)["token"]
                       for name in ("writer", "outsider", "observer")}
        self.store = HostRequestStore(self.root / "mtr-metadata.sqlite3")

    def api(self, route, payload, token=None):
        return pinned_https_json(
            self.url + "/api/mtr/v2/" + route, self.pin,
            method="POST", data=payload,
            headers={"Authorization": "Bearer " + (token or self.tokens["writer"])},
        )

    def mount(self):
        self.service.mount_mtr_finance_pilot(self.store, org_id="synthetic-office")

    @staticmethod
    def prepare_body(request_id="a" * 32, prepare_key="prepare-alpha"):
        return {"requestId": request_id, "taskId": CARD,
                "prepareKey": prepare_key, "manualAction": True}

    @staticmethod
    def send_body(prepared, send_key="send-alpha"):
        return {"requestId": prepared["requestId"], "taskId": CARD,
                "sendKey": send_key, "payloadSha256": prepared["payloadSha256"],
                "baseRevision": prepared["baseRevision"], "manualAction": True}

    def error(self, status, action, body, token=None):
        with self.assertRaises(HTTPError) as caught:
            self.api(action, body, token)
        self.assertEqual(caught.exception.code, status)
        return json.loads(caught.exception.read())

    def test_pilot_is_default_off_even_on_live_tls_server(self):
        self.error(404, "prepare", self.prepare_body())
        self.mount()
        with self.assertRaises(RuntimeError):
            self.mount()

    def test_prepare_manual_intent_query_first_no_peer_or_financial_writes(self):
        self.mount()
        prepared = self.api("prepare", self.prepare_body())
        self.assertEqual(prepared["requestState"], "PREPARED")
        self.assertEqual(prepared["receiptState"], "unknown")
        self.assertFalse(prepared["transportCalled"])
        self.assertFalse(prepared["financialEventCreated"])
        replay = self.api("prepare", self.prepare_body())
        self.assertTrue(replay["idempotent"])
        self.assertEqual(prepared["payloadSha256"], replay["payloadSha256"])
        self.assertEqual(prepared["baseRevision"], replay["baseRevision"])
        sent = self.api("manual-send", self.send_body(prepared))
        self.assertEqual(sent["requestState"], "MANUAL_SEND_AUTHORIZED")
        self.assertEqual(sent["nextAction"], "query_taraz_first_hold_unknown")
        self.assertFalse(sent["transportCalled"])
        self.assertFalse(sent["financialEventCreated"])
        self.assertTrue(self.api("manual-send", self.send_body(prepared))["idempotent"])
        status = self.api("status", {"requestId": prepared["requestId"],
                                     "taskId": CARD, "baseRevision": prepared["baseRevision"]})
        self.assertEqual(status["receiptState"], "unknown")
        self.assertNotIn("payload", status)
        self.assertNotIn("title", status)
        self.assertNotIn("amountRial", status)
        self.error(403, "status", {"requestId": prepared["requestId"],
                                   "taskId": "example-1",
                                   "baseRevision": prepared["baseRevision"]})

    def test_wrong_role_scope_token_and_changed_idempotency_fail_closed(self):
        self.mount()
        p = self.prepare_body()
        self.error(403, "prepare", p, token=self.tokens["observer"])
        self.error(403, "prepare", p, token=self.tokens["outsider"])
        self.error(403, "prepare", p, token="fabricated")
        created = self.api("prepare", p)
        self.error(409, "prepare", self.prepare_body("b" * 32, "prepare-alpha"))
        self.error(409, "prepare", self.prepare_body("a" * 32, "prepare-beta"))
        self.error(403, "status", {"requestId": created["requestId"],
                                   "taskId": CARD, "baseRevision": created["baseRevision"]},
                   token=self.owner_token)
        self.error(403, "manual-send", self.send_body(created),
                   token=self.tokens["outsider"])

    def test_saved_card_version_change_rejects_prepare_replay_and_send(self):
        self.mount()
        prepared = self.api("prepare", self.prepare_body())
        state = self.bridge.getState()
        next(t for t in state["tasks"] if t["id"] == CARD)["title"] = "changed-saved-title"
        self.bridge.saveState(state)
        self.error(409, "manual-send", self.send_body(prepared))
        self.error(409, "prepare", self.prepare_body())
        # Readback of the historical request remains possible after card edits;
        # only new transmission authorizations must reject a stale baseline.
        status = self.api("status", {"requestId": prepared["requestId"],
                                     "taskId": CARD, "baseRevision": prepared["baseRevision"]})
        self.assertEqual(status["receiptState"], "unknown")

    def test_bad_manual_flags_field_injection_and_oversized_body(self):
        self.mount()
        request = self.prepare_body()
        self.error(403, "prepare", {**request, "manualAction": False})
        self.error(400, "prepare", {**request, "orgId": "other-org"})
        self.error(400, "prepare", {**request, "payload": {"amountRial": "999"}})
        self.error(403, "prepare", {**request, "manualAction": "true"})
        self.error(413, "prepare", {**request, "junk": "x" * 5000})
        self.error(404, "receipt-ingest", request)

    def test_role_revocation_is_immediate_and_request_persists(self):
        self.mount()
        saved = self.api("prepare", self.prepare_body())
        self.service.upsert_user(self.owner_token, {
            "username": "writer", "role": "editor", "projects": ["p-sample"],
            "financeEdit": False,
        })
        self.error(403, "status", {"requestId": saved["requestId"],
                                   "taskId": CARD, "baseRevision": saved["baseRevision"]})
        self.assertTrue(self.store.path.exists())

    def test_removed_saved_project_denies_new_manual_finance_prepare(self):
        """A surviving orphan card never authorizes finance for a deleted project."""
        self.mount()
        snapshot = self.bridge.getState()
        snapshot["projects"] = [p for p in snapshot["projects"]
                                if p["id"] != "p-sample"]
        with patch.object(self.bridge, "getState", return_value=snapshot):
            self.error(403, "prepare", self.prepare_body("c" * 32))
        with self.store._connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0], 0)

    def test_invalid_private_project_grant_shape_never_authorizes_prepare(self):
        """String membership must never be mistaken for a host project grant."""
        self.mount()
        with self.service.lock:
            original = self.service.users["writer"]["projects"]
            self.service.users["writer"]["projects"] = "p-sample"
        try:
            self.error(403, "prepare", self.prepare_body("d" * 32))
        finally:
            with self.service.lock:
                self.service.users["writer"]["projects"] = original
        with self.store._connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0], 0)

    def test_missing_private_project_grant_field_is_not_unrestricted_access(self):
        """Corrupt account dictionaries cannot interpret missing scope as all."""
        self.mount()
        with self.service.lock:
            grants = self.service.users["writer"].pop("projects")
        try:
            self.error(403, "prepare", self.prepare_body("f" * 32))
        finally:
            with self.service.lock:
                self.service.users["writer"]["projects"] = grants
        with self.store._connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0], 0)

    def test_missing_private_project_scope_cannot_mint_recovery_principal(self):
        """Recovery must not reinterpret a corrupt/missing scope as global."""
        self.mount()
        with self.service.lock:
            grants = self.service.users["writer"].pop("projects")
        try:
            with self.assertRaises(PermissionError):
                self.service.mtr_finance_adapter._recovery_principal(
                    self.tokens["writer"]
                )
        finally:
            with self.service.lock:
                self.service.users["writer"]["projects"] = grants

    def test_unreadable_host_state_is_explicitly_denied_before_prepare(self):
        self.mount()
        with patch.object(self.bridge, "getState", return_value=None):
            self.error(403, "prepare", self.prepare_body("e" * 32))
        with self.store._connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0], 0)

    def test_bad_pin_fails_before_transmitting_session_token(self):
        self.mount()
        with self.assertRaises(Exception) as raised:
            pinned_https_json(self.url + "/api/mtr/v2/prepare", "0" * 64,
                              method="POST", data=self.prepare_body(),
                              headers={"Authorization": "Bearer " + self.tokens["writer"]})
        self.assertIn("certificate fingerprint mismatch", str(raised.exception))

    def test_duplicate_json_properties_rejected_over_pinned_tls(self):
        self.mount()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE  # Test-only; verify the pin first.
        connection = HTTPSConnection("127.0.0.1", self.port, timeout=5,
                                     context=context)
        try:
            connection.connect()
            self.assertEqual(
                hashlib.sha256(connection.sock.getpeercert(binary_form=True)).hexdigest(),
                self.pin,
            )
            raw = (b'{"requestId":"' + b"a" * 32 + b'","requestId":"'
                   + b"b" * 32 + b'","taskId":"example-2",'
                   + b'"prepareKey":"prepare-alpha","manualAction":true}')
            connection.request("POST", "/api/mtr/v2/prepare", body=raw,
                               headers={"Authorization": "Bearer " + self.tokens["writer"],
                                        "Content-Type": "application/json"})
            reply = connection.getresponse()
            self.assertEqual(reply.status, 400)
            reply.read()
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
