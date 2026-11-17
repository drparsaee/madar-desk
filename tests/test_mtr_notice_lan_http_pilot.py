"""Synthetic E6 internal inbox over an explicitly mounted HTTPS LAN host."""
import hashlib
from http.client import HTTPSConnection
import json
from pathlib import Path
import ssl
import tempfile
from threading import RLock
import unittest
from urllib.error import HTTPError

from lan import LanService, pinned_https_json, certificate_fingerprint
from mtr_lan_notification_adapter import TrustedHostNoticeEvent, _sha_task
from mtr_internal_notification_store import InternalNotificationStore
from tests.test_lan_tls import _CERT, _KEY


class SyntheticBridge:
    def __init__(self):
        self._lock = RLock()
        self.state = {
            "projects": [{"id": "p-sample", "name": "Synthetic"}],
            "tasks": [{"id": "task-one", "projectId": "p-sample",
                       "title": "Synthetic task", "assignees": ["writer", "viewer"]}],
        }

    def getState(self):
        from copy import deepcopy
        return deepcopy(self.state)


class E6MountedTlsPilotTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="mtr-notice-tls-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        cert, key = self.root / "test.crt", self.root / "test.key"
        cert.write_text(_CERT, encoding="ascii")
        key.write_text(_KEY, encoding="ascii")
        self.bridge = SyntheticBridge()
        self.service = LanService(self.bridge, self.root / "users.json",
                                  bind="127.0.0.1", port=0,
                                  certfile=cert, keyfile=key)
        self.service.setup_owner("owner", "synthetic-owner-passphrase")
        port = self.service.start()
        self.addCleanup(self.service.stop)
        self.url = f"https://127.0.0.1:{port}/api/mtr-notices/v1/command"
        self.pin = certificate_fingerprint(cert)
        self.owner = self.service.authenticate("owner", "synthetic-owner-passphrase")["token"]
        for name, role in (("writer", "editor"), ("viewer", "viewer"),
                           ("outsider", "editor")):
            self.service.upsert_user(self.owner, {
                "username": name, "password": "synthetic-user-passphrase",
                "role": role, "projects": ["p-sample"],
            })
        for account in self.service.users.values():
            account["internalNotificationsEnabled"] = True
        # Test fixture mutation ONLY: the current production user-admin UI does
        # not offer this opt-in control. Keep this explicitly pilot-only.
        self.service._store_users()
        self.users = {name: self.service.authenticate(name, "synthetic-user-passphrase")["token"]
                      for name in ("writer", "viewer", "outsider")}
        self.store = InternalNotificationStore(self.root / "notices.sqlite3")
        self.events = {"evt-one": TrustedHostNoticeEvent(
            event_key="evt-one", task_id="task-one",
            task_sha256=_sha_task(self.bridge.getState()["tasks"][0]),
            project_id="p-sample", original_request_id="req-one",
            event_kind="request_status_changed", actor_id="writer",
            occurred_at="2026-11-09T15:00:00Z", previous_revision=1,
            revision=2, previous_status="READY_TO_SUBMIT",
            status="UNDER_FINANCE_REVIEW",
        )}

    @staticmethod
    def cmd(action, params):
        return {"schemaVersion": 1, "action": action, "params": params}

    def mount(self):
        self.service.mount_mtr_notice_pilot(
            self.store, org_id="synthetic-office",
            trusted_event_source=self.events.get,
        )

    def call(self, action, params, *, token=None):
        return pinned_https_json(
            self.url, self.pin, method="POST", data=self.cmd(action, params),
            headers={"Authorization": "Bearer " + (token or self.owner)},
        )

    def fail(self, code, action, params, *, token=None):
        with self.assertRaises(HTTPError) as raised:
            self.call(action, params, token=token)
        self.assertEqual(raised.exception.code, code)
        return json.loads(raised.exception.read())

    def test_disabled_without_explicit_mount_and_tls(self):
        self.fail(404, "list", {})
        self.mount()
        with self.assertRaises(RuntimeError):
            self.mount()

    def test_pinned_tls_publish_list_read_dedup_and_redaction(self):
        self.mount()
        inserted = self.call("publish", {"eventKey": "evt-one", "manualAction": True},
                             token=self.users["writer"])
        self.assertEqual(inserted["result"]["inserted"], 3)
        self.assertFalse(inserted["result"]["taraz_posting_performed"])
        replay = self.call("publish", {"eventKey": "evt-one", "manualAction": True},
                           token=self.users["writer"])
        self.assertEqual(replay["result"]["replayed"], 3)
        viewer = self.call("list", {}, token=self.users["viewer"])["result"]
        self.assertEqual(len(viewer), 1)
        self.assertEqual(viewer[0]["channel"], "internal_only")
        self.assertIsNone(viewer[0]["actor_id"])
        self.assertEqual(viewer[0]["status"], "UNDER_FINANCE_REVIEW")
        self.assertNotIn("receipt_reference", viewer[0])
        self.assertEqual(self.call("list", {}, token=self.users["outsider"])["result"], [])
        note_id = viewer[0]["notice_id"]
        read = self.call("mark-read", {"noticeId": note_id, "manualAction": True},
                         token=self.users["viewer"])["result"]
        self.assertTrue(read["marked_read"])
        self.assertTrue(self.call("list", {}, token=self.users["viewer"])["result"][0]["is_read"])
        self.fail(403, "mark-read", {"noticeId": note_id, "manualAction": True},
                  token=self.users["outsider"])

    def test_bad_session_manual_flags_and_untrusted_event_fields_fail_closed(self):
        self.mount()
        self.fail(403, "publish", {"eventKey": "evt-one", "manualAction": False},
                  token=self.users["writer"])
        self.fail(403, "publish", {"eventKey": "evt-one", "manualAction": True},
                  token=self.users["viewer"])
        self.fail(400, "publish", {"eventKey": "evt-one", "manualAction": True,
                                    "orgId": "forged"}, token=self.users["writer"])
        self.fail(400, "list", {"recipientId": "writer"})
        self.fail(403, "list", {}, token="forged-token")

    def test_wrong_certificate_pin_and_duplicate_json_rejected(self):
        self.mount()
        with self.assertRaises(ssl.SSLCertVerificationError):
            pinned_https_json(self.url, "0" * 64, method="POST",
                              data=self.cmd("list", {}),
                              headers={"Authorization": "Bearer " + self.owner})
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        connection = HTTPSConnection("127.0.0.1", self.service.port,
                                     timeout=5, context=ctx)
        try:
            connection.connect()
            self.assertEqual(hashlib.sha256(connection.sock.getpeercert(
                binary_form=True)).hexdigest(), self.pin)
            body = b'{"schemaVersion":1,"action":"list","action":"publish","params":{}}'
            connection.request("POST", "/api/mtr-notices/v1/command", body,
                               {"Authorization": "Bearer " + self.owner,
                                "Content-Type": "application/json"})
            response = connection.getresponse()
            self.assertEqual(response.status, 400)
            response.read()
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
