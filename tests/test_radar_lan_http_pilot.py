"""Opt-in Radar E1 HTTPS host integration with disposable contacts only."""
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
from radar_crm_store import RadarCrmStore
from tests.test_lan_tls import _CERT, _KEY


PASSWORD = "synthetic-radar-https-password"
T0 = "2026-11-09T15:00:00+00:00"
T1 = "2026-11-09T16:00:00+00:00"


class RadarMountedTlsPilotTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="radar-https-test-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        with patch.object(native_app, "datadir", return_value=self.root):
            bridge = native_app.Bridge()
            bridge.saveState(native_app.initial_state())
        cert = self.root / "test.crt"
        key = self.root / "test.key"
        cert.write_text(_CERT, encoding="ascii")
        key.write_text(_KEY, encoding="ascii")
        self.service = LanService(bridge, self.root / "users.json",
                                  bind="127.0.0.1", port=0,
                                  certfile=cert, keyfile=key)
        self.service.setup_owner("owner", PASSWORD)
        port = self.service.start()
        self.addCleanup(self.service.stop)
        self.url = f"https://127.0.0.1:{port}/api/radar/v1/command"
        self.pin = certificate_fingerprint(cert)
        self.owner = self.service.authenticate("owner", PASSWORD)["token"]
        for name, role, projects in (
            ("writer", "editor", ["p-sample"]),
            ("other", "editor", ["p-personal"]),
            ("viewer", "viewer", ["p-sample"]),
        ):
            self.service.upsert_user(self.owner, {
                "username": name, "role": role, "projects": projects,
                "password": PASSWORD,
            })
        self.tokens = {name: self.service.authenticate(name, PASSWORD)["token"]
                       for name in ("writer", "other", "viewer")}
        self.store = RadarCrmStore(self.root / "radar.sqlite")

    @staticmethod
    def command(action, params, *, project="p-sample", human=True):
        record = {"schemaVersion": 1, "action": action,
                  "projectId": project, "params": params}
        if action not in {"get_contact", "list_contacts", "list_history",
                          "list_due_reminders"}:
            record["manualAction"] = human
        return record

    def call(self, record, token=None):
        return pinned_https_json(self.url, self.pin, method="POST", data=record,
                                 headers={"Authorization": "Bearer " + (token or self.owner)})

    def fail(self, status, record, token=None):
        with self.assertRaises(HTTPError) as error:
            self.call(record, token)
        self.assertEqual(error.exception.code, status)
        return json.loads(error.exception.read())

    def mount(self):
        self.service.mount_radar_crm_pilot(self.store, org_id="synthetic-office")

    def create(self, contact="contact-one", event="evt-create"):
        return self.command("create_contact", {
            "contactId": contact, "eventId": event, "occurredAt": T0,
            "name": "Synthetic customer", "assigneeId": "writer",
        })

    def test_disabled_by_default_on_https_and_no_plain_http_mount(self):
        self.fail(404, self.create())
        self.mount()
        with self.assertRaises(RuntimeError):
            self.mount()

    def test_live_pinned_tls_human_create_note_read_and_replay(self):
        self.mount()
        created = self.call(self.create())
        self.assertEqual(created["result"]["version"], 1)
        self.assertFalse(created["result"]["replayed"])
        repeated = self.call(self.create())
        self.assertTrue(repeated["result"]["replayed"])
        note = self.command("record_note", {
            "contactId": "contact-one", "eventId": "evt-note",
            "occurredAt": T1, "expectedVersion": 1,
            "note": "synthetic conversation", "channel": "call",
        })
        self.assertEqual(self.call(note, self.tokens["writer"])["result"]["version"], 2)
        found = self.call(self.command("get_contact", {"contactId": "contact-one"}),
                          self.tokens["writer"])
        self.assertEqual(found["result"]["name"], "Synthetic customer")
        self.assertEqual(found["result"]["version"], 2)
        self.assertEqual(self.call(self.command("list_history", {
            "contactId": "contact-one"}), self.tokens["writer"])["result"][1]["kind"],
                         "interaction_recorded")

    def test_acl_and_client_organization_injection_rejected(self):
        self.mount()
        self.fail(403, self.create(), self.tokens["viewer"])
        self.fail(403, self.create(), self.tokens["other"])
        self.fail(403, self.create(), "invalid-token")
        self.fail(400, {**self.create(), "orgId": "other-org"})
        self.fail(400, self.command("create_contact", {
            **self.create()["params"], "tarazPartyId": "forged",
        }))
        self.fail(400, self.command("create_contact", self.create()["params"],
                                    human=False))
        self.call(self.create())
        self.fail(403, self.command("get_contact", {"contactId": "contact-one"}),
                  self.tokens["other"])

    def test_conflict_and_stale_version(self):
        self.mount()
        self.call(self.create())
        changed = self.command("record_note", {
            "contactId": "contact-one", "eventId": "evt-next",
            "occurredAt": T1, "expectedVersion": 1, "note": "valid",
        })
        self.call(changed, self.tokens["writer"])
        stale = self.command("record_note", {
            "contactId": "contact-one", "eventId": "evt-another",
            "occurredAt": T1, "expectedVersion": 1, "note": "stale",
        })
        self.fail(409, stale, self.tokens["writer"])

    def test_duplicate_raw_json_and_bad_tls_pin(self):
        self.mount()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        connection = HTTPSConnection("127.0.0.1", self.service.port,
                                     timeout=5, context=context)
        try:
            connection.connect()
            self.assertEqual(hashlib.sha256(
                connection.sock.getpeercert(binary_form=True)).hexdigest(), self.pin)
            body = b'{"schemaVersion":1,"action":"list_contacts","action":"create_contact","projectId":"p-sample","params":{}}'
            connection.request("POST", "/api/radar/v1/command", body,
                               {"Authorization": "Bearer " + self.owner,
                                "Content-Type": "application/json"})
            response = connection.getresponse()
            self.assertEqual(response.status, 400)
            response.read()
        finally:
            connection.close()
        with self.assertRaises(ssl.SSLCertVerificationError):
            pinned_https_json(self.url, "0" * 64, method="POST", data=self.create(),
                              headers={"Authorization": "Bearer " + self.owner})


if __name__ == "__main__":
    unittest.main()
