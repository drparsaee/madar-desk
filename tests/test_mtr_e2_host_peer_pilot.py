"""One MadarHost session -> durable one-shot gate -> real TLS test Taraz.

All data are synthetic in TemporaryDirectory; no installed service is used.
This class inherits peer/interoperability scenarios as adjacent regression.
"""
from pathlib import Path
import hashlib
import ssl
from threading import Thread
import unittest
from unittest.mock import patch

import native_app
from lan import LanService, pinned_https_json
from mtr_e2_dispatch_gate import OneShotDispatchGate, DispatchGateConflict
from mtr_e2_host_peer_pilot import MtrE2HostPeerPilot, HostPeerPilotDenied
from mtr_e2_query_observation_journal import QueryObservationJournal, QueryJournalError
from mtr_host_principal_provenance import GATE_RECOVERY, OUTBOX_RECOVERY
from mtr_host_request_store import HostRequestStore, StoreConflict
from mtr_lan_finance_adapter import MtrLanFinanceAdapter
from mtr_peer_https_pilot import PeerPilotUncertain
from tests import test_mtr_e2_two_source_https_pilot as peer_tests

KEYS = peer_tests.KEYS


PASS = "synthetic-madar-host-passphrase-123"
CARD = "example-2"


class HostToPeerIntegratedTests(peer_tests.MtrTwoSourceHttpsTests):
    def setUp(self):
        super().setUp()
        with patch.object(native_app, "datadir", return_value=self.root):
            bridge = native_app.Bridge()
            bridge.saveState(native_app.initial_state())
        self.bridge = bridge
        host_cert = self.root / "host-test.crt"
        host_key = self.root / "host-test.key"
        host_cert.write_text(self.pem_cert, encoding="ascii")
        host_key.write_text(self.pem_key, encoding="ascii")
        self.host_cert = host_cert
        self.host = LanService(bridge, self.root / "host-users.json",
                               bind="127.0.0.1", port=0,
                               certfile=host_cert, keyfile=host_key)
        self.host.setup_owner("owner", PASS)
        owner = self.host.authenticate("owner", PASS)["token"]
        self.host.upsert_user(owner, {
            "username": "editor", "role": "editor", "projects": ["p-sample"],
            "financeEdit": True, "password": PASS,
        })
        self.token = self.host.authenticate("editor", PASS)["token"]
        self.outbox = HostRequestStore(self.root / "host-outbox.sqlite3")
        self.adapter = MtrLanFinanceAdapter(self.host, self.outbox,
                                            org_id="office-one")
        self.gate = OneShotDispatchGate(self.root / "host-dispatch.sqlite3",
                                        self.outbox)
        self.journal = QueryObservationJournal(
            self.root / "host-peer-observations.sqlite3",
            outbox=self.outbox, gate=self.gate,
        )
        self.coordinator = MtrE2HostPeerPilot(
            finance_adapter=self.adapter, dispatch_gate=self.gate,
            peer=self.client, keys=KEYS, synthetic_only=True,
            observation_journal=self.journal,
        )
        task = next(t for t in self.bridge.getState()["tasks"]
                    if t["id"] == CARD)
        self.revision = self.adapter._task_revision(task)

    def authorize(self):
        prepared = self.adapter.handle("prepare", self.token, {
            "requestId": self.request_id, "taskId": CARD,
            "prepareKey": "prepare-synthetic-1", "manualAction": True,
        })
        sent = self.adapter.handle("manual-send", self.token, {
            "requestId": self.request_id, "taskId": CARD,
            "sendKey": "synthetic-send-key-1",
            "payloadSha256": prepared["payloadSha256"],
            "baseRevision": prepared["baseRevision"], "manualAction": True,
        })
        self.assertEqual(sent["requestState"], "MANUAL_SEND_AUTHORIZED")
        return prepared["payloadSha256"]

    def send(self, digest, *, token=None, human=True):
        return self.coordinator.send_once(
            token=token or self.token, task_id=CARD,
            request_id=self.request_id, base_revision=self.revision,
            payload_sha256=digest, send_key="synthetic-send-key-1",
            explicit_manual_action=human,
        )

    def assert_only_one_arrival(self):
        with self.registry._connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0], 1)

    def test_current_host_principal_one_shot_signed_roundtrip(self):
        digest = self.authorize()
        result = self.send(digest)
        self.assertTrue(result["metadataArrivalHint"])
        self.assertTrue(result["dispatchSlotConsumed"])
        self.assertFalse(result["canAutoRetry"])
        self.assertFalse(result["financialEventCreated"])
        self.assertFalse(result["officialTarazReceipt"])
        self.assert_only_one_arrival()
        with self.assertRaises(DispatchGateConflict):
            self.send(digest)
        observation = self.coordinator.query_first(
            token=self.token, task_id=CARD, request_id=self.request_id,
            base_revision=self.revision,
        )
        self.assertEqual(observation["lookupStatus"], "received")
        self.assertFalse(observation["officialTarazReceipt"])
        rows = self.journal.observations(
            principal=self.adapter._recovery_principal(self.token),
            request_id=self.request_id, expected_base_revision=self.revision,
            token=self.token,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["signedPeerEnvelopeSha256"],
                         observation["signedPeerEnvelopeSha256"])
        self.assertFalse(rows[0]["canAutoRetry"])
        self.assert_only_one_arrival()

    def test_signed_query_journal_failure_never_reports_success_or_rearms(self):
        digest = self.authorize()
        self.send(digest)
        with patch.object(self.journal, "record", side_effect=QueryJournalError("full")):
            with self.assertRaisesRegex(QueryJournalError, "full"):
                self.coordinator.query_first(
                    token=self.token, task_id=CARD, request_id=self.request_id,
                    base_revision=self.revision,
                )
        self.assertEqual(self.journal.observations(
            principal=self.adapter._recovery_principal(self.token),
            request_id=self.request_id, expected_base_revision=self.revision,
            token=self.token,
        ), ())
        with self.assertRaises(DispatchGateConflict):
            self.send(digest)
        self.assert_only_one_arrival()

    def test_revoked_host_finance_permission_before_signed_evidence_is_denied(self):
        digest = self.authorize()
        self.send(digest)
        original = self.client.query_verified

        def revoke_during_peer(*args, **kwargs):
            callback = kwargs["evidence_sink"]
            def before_persist(*wires):
                self.host.users["editor"]["financeEdit"] = False
                return callback(*wires)
            return original(*args, **{**kwargs, "evidence_sink": before_persist})

        with patch.object(self.client, "query_verified", side_effect=revoke_during_peer):
            with self.assertRaises(PermissionError):
                self.coordinator.query_first(
                    token=self.token, task_id=CARD, request_id=self.request_id,
                    base_revision=self.revision,
                )
        self.host.users["editor"]["financeEdit"] = True
        self.assertEqual(self.journal.observations(
            principal=self.adapter._recovery_principal(self.token),
            request_id=self.request_id, expected_base_revision=self.revision,
            token=self.token,
        ), ())
        self.assert_only_one_arrival()

    def test_real_host_delete_and_recreate_username_cannot_read_old_finance_request(self):
        digest = self.authorize()
        self.send(digest)
        old_principal = self.adapter._recovery_principal(self.token)
        owner = self.host.authenticate("owner", PASS)["token"]
        self.host.delete_user(owner, "editor")
        self.host.upsert_user(owner, {
            "username": "editor", "role": "editor", "projects": ["p-sample"],
            "financeEdit": True, "password": PASS,
        })
        self.token = self.host.authenticate("editor", PASS)["token"]
        fresh = self.adapter._recovery_principal(self.token)
        self.assertNotEqual(old_principal.user_id, fresh.user_id,
                            "new account generation must not inherit historical identity")
        with self.assertRaises(PermissionError):
            self.coordinator.query_first(
                token=self.token, task_id=CARD, request_id=self.request_id,
                base_revision=self.revision,
            )
        self.assert_only_one_arrival()

    def test_no_manual_action_or_no_saved_host_authorization_never_sends(self):
        with self.assertRaises((KeyError, StoreConflict)):
            self.send("f" * 64)
        self.assertEqual(self.server.peer_registry.path, self.registry.path)
        digest = self.authorize()
        with self.assertRaises(PermissionError):
            self.send(digest, human=False)
        with self.registry._connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0], 0)

    def test_changed_saved_card_or_revoked_role_blocks_transport(self):
        digest = self.authorize()
        self.host.users["editor"]["financeEdit"] = False
        with self.assertRaises(PermissionError):
            self.send(digest)
        self.host.users["editor"]["financeEdit"] = True
        state = self.bridge.getState()
        next(item for item in state["tasks"] if item["id"] == CARD)["title"] = "changed"
        self.bridge.saveState(state)
        with self.assertRaises(StoreConflict):
            self.send(digest)
        with self.registry._connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0], 0)

    def test_lost_http_ack_still_forbids_repeat_after_host_restart(self):
        digest = self.authorize()
        original = self.client._post

        def lose_ack(route, wire, *, response_is_envelope):
            original(route, wire, response_is_envelope=response_is_envelope)
            raise PeerPilotUncertain("simulated lost response after actual commit")

        with patch.object(self.client, "_post", side_effect=lose_ack):
            with self.assertRaises(PeerPilotUncertain):
                self.send(digest)
        self.assert_only_one_arrival()
        reopened = OneShotDispatchGate(self.gate.path,
                                       HostRequestStore(self.outbox.path))
        with self.assertRaises(DispatchGateConflict):
            reopened.reserve_once(
                principal=self.adapter._principal_and_task(self.token, CARD)[0],
                request_id=self.request_id,
                expected_payload_sha256=digest,
                expected_base_revision=self.revision,
                current_server_revision=self.revision,
                send_key="synthetic-send-key-1",
            )
        observation = self.coordinator.query_first(
            token=self.token, task_id=CARD, request_id=self.request_id,
            base_revision=self.revision,
        )
        self.assertEqual(observation["lookupStatus"], "received")
        self.assertFalse(observation["canAutoRetry"])
        self.assert_only_one_arrival()

    def test_real_two_https_hops_manual_client_host_then_test_taraz(self):
        """Real pinned client->MadarHost and MadarHost->Taraz loopback TLS."""
        self.host.start()
        self.addCleanup(self.host.stop)
        self.host.mount_mtr_finance_pilot(self.outbox, org_id=KEYS.organization_id)
        host_pin = hashlib.sha256(ssl.PEM_cert_to_DER_cert(self.pem_cert)).hexdigest()
        uri = f"https://127.0.0.1:{self.host.port}/api/mtr/v2/"

        def call(action, payload):
            return pinned_https_json(
                uri + action, host_pin, method="POST", data=payload,
                headers={"Authorization": "Bearer " + self.token},
            )

        prepared = call("prepare", {
            "requestId": self.request_id, "taskId": CARD,
            "prepareKey": "prepare-synthetic-1", "manualAction": True,
        })
        self.assertEqual(prepared["requestState"], "PREPARED")
        authorized = call("manual-send", {
            "requestId": self.request_id, "taskId": CARD,
            "sendKey": "synthetic-send-key-1", "manualAction": True,
            "baseRevision": prepared["baseRevision"],
            "payloadSha256": prepared["payloadSha256"],
        })
        self.assertEqual(authorized["requestState"], "MANUAL_SEND_AUTHORIZED")
        self.assertFalse(authorized["transportCalled"])
        sent = self.send(prepared["payloadSha256"])
        self.assertTrue(sent["metadataArrivalHint"])
        self.assertFalse(sent["officialTarazReceipt"])
        host_status = call("status", {
            "requestId": self.request_id, "taskId": CARD,
            "baseRevision": prepared["baseRevision"],
        })
        self.assertEqual(host_status["receiptState"], "unknown")
        self.assertFalse(host_status["financialEventCreated"])
        peer_status = self.coordinator.query_first(
            token=self.token, task_id=CARD, request_id=self.request_id,
            base_revision=self.revision,
        )
        self.assertEqual(peer_status["lookupStatus"], "received")
        self.assertFalse(peer_status["officialTarazReceipt"])
        with self.assertRaises(DispatchGateConflict):
            self.send(prepared["payloadSha256"])
        self.assert_only_one_arrival()

    def test_changed_title_allows_old_signed_query_but_never_a_second_send(self):
        digest = self.authorize()
        self.send(digest)
        state = self.bridge.getState()
        next(item for item in state["tasks"] if item["id"] == CARD)["title"] = "new saved title"
        self.bridge.saveState(state)
        # The already signed *original* request must remain recoverable, even
        # when a legitimate later edit changes the current card revision.
        observation = self.coordinator.query_first(
            token=self.token, task_id=CARD, request_id=self.request_id,
            base_revision=self.revision,
        )
        self.assertEqual(observation["lookupStatus"], "received")
        with self.assertRaises(StoreConflict):
            self.send(digest)
        self.assert_only_one_arrival()

    def test_blocking_peer_transport_does_not_hold_shared_host_or_card_locks(self):
        """Other LAN users must not stall on a slow external TLS exchange."""
        digest = self.authorize()
        calls = []

        def prove_locks_available():
            acquired = []

            def concurrent_client():
                # Both locks must be available to an independent LAN thread
                # while the current one is inside a peer network callback.
                with self.host.lock, self.bridge._lock:
                    acquired.append(True)

            thread = Thread(target=concurrent_client, daemon=True)
            thread.start()
            thread.join(timeout=0.8)
            self.assertFalse(thread.is_alive(), "peer held shared host/card locks")
            self.assertEqual(acquired, [True])
            calls.append("locks_released_during_peer")

        original_send = self.client.intake_once

        def inspected_send(*args, **kwargs):
            prove_locks_available()
            return original_send(*args, **kwargs)

        with patch.object(self.client, "intake_once", side_effect=inspected_send):
            sent = self.send(digest)
        self.assertTrue(sent["metadataArrivalHint"])

        original_query = self.client.query_verified

        def inspected_query(*args, **kwargs):
            prove_locks_available()
            return original_query(*args, **kwargs)

        with patch.object(self.client, "query_verified", side_effect=inspected_query):
            recovered = self.coordinator.query_first(
                token=self.token, task_id=CARD, request_id=self.request_id,
                base_revision=self.revision,
            )
        self.assertEqual(recovered["lookupStatus"], "received")
        self.assertEqual(calls, ["locks_released_during_peer"] * 2)
        with self.assertRaises(DispatchGateConflict):
            self.send(digest)
        self.assert_only_one_arrival()

    def test_same_actor_relogin_signed_query_only_without_rearming_dispatch(self):
        digest = self.authorize()
        self.send(digest)
        new_token = self.host.authenticate("editor", PASS)["token"]
        self.assertNotEqual(new_token, self.token)
        current = self.adapter._recovery_principal(new_token)
        # Ordinary outbox/gate APIs MUST remain bound to the original session;
        # the dedicated recovery path is narrower and cannot authorize send.
        with self.assertRaises(PermissionError):
            self.outbox.request_snapshot(
                principal=current, request_id=self.request_id,
                expected_base_revision=self.revision,
            )
        with self.assertRaises(PermissionError):
            self.gate.status(
                principal=current, request_id=self.request_id,
                expected_base_revision=self.revision,
            )
        status = self.gate.recovery_status(
            principal=current, request_id=self.request_id,
            expected_base_revision=self.revision,
            token=new_token,
            gate_seal=self.coordinator._provenance.issue_recovery(
                new_token, audience=GATE_RECOVERY),
            outbox_seal=self.coordinator._provenance.issue_recovery(
                new_token, audience=OUTBOX_RECOVERY),
        )
        self.assertTrue(status["reservationConsumed"])
        self.assertFalse(status["mayDispatch"])
        recovered = self.coordinator.query_first(
            token=new_token, task_id=CARD, request_id=self.request_id,
            base_revision=self.revision,
        )
        self.assertEqual(recovered["lookupStatus"], "received")
        self.assertFalse(recovered["officialTarazReceipt"])
        with self.assertRaises((PermissionError, StoreConflict)):
            self.send(digest, token=new_token)
        self.assert_only_one_arrival()

    def test_relogin_recovery_requires_current_actor_role_project_and_request(self):
        digest = self.authorize()
        self.send(digest)
        owner_token = self.host.authenticate("owner", PASS)["token"]
        with self.assertRaises(PermissionError):
            self.coordinator.query_first(
                token=owner_token, task_id=CARD, request_id=self.request_id,
                base_revision=self.revision,
            )
        new_token = self.host.authenticate("editor", PASS)["token"]
        with self.assertRaises(HostPeerPilotDenied):
            self.coordinator.query_first(
                token=new_token, task_id="another-card",
                request_id=self.request_id, base_revision=self.revision,
            )
        self.host.users["editor"]["financeEdit"] = False
        with self.assertRaises(PermissionError):
            self.coordinator.query_first(
                token=new_token, task_id=CARD, request_id=self.request_id,
                base_revision=self.revision,
            )
        self.host.users["editor"]["financeEdit"] = True
        self.host.users["editor"]["projects"] = []
        with self.assertRaises(PermissionError):
            self.coordinator.query_first(
                token=new_token, task_id=CARD, request_id=self.request_id,
                base_revision=self.revision,
            )
        self.assert_only_one_arrival()

    def test_deleted_saved_card_does_not_destroy_same_actor_query_first(self):
        digest = self.authorize()
        self.send(digest)
        state = self.bridge.getState()
        state["tasks"] = [task for task in state["tasks"] if task["id"] != CARD]
        self.bridge.saveState(state)
        new_token = self.host.authenticate("editor", PASS)["token"]
        observation = self.coordinator.query_first(
            token=new_token, task_id=CARD, request_id=self.request_id,
            base_revision=self.revision,
        )
        self.assertEqual(observation["lookupStatus"], "received")
        with self.assertRaises(PermissionError):
            self.send(digest, token=new_token)
        self.assert_only_one_arrival()


if __name__ == "__main__":
    unittest.main()
