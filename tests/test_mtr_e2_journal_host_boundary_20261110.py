"""Host/journal negative-boundary QA; synthetic local databases and loopback only.

This test module intentionally does not inherit the full integration suite,
which would duplicate its test methods. Instead, each case owns and closes a
single pre-existing, disposable two-source fixture.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from threading import Event, Thread
import unittest
from unittest.mock import patch

from mtr_e2_dispatch_gate import DispatchGateConflict
from mtr_e2_query_observation_journal import (
    QueryJournalConflict, QueryJournalError, QueryObservationJournal,
)
from mtr_host_principal_provenance import GATE_RECOVERY, OUTBOX_RECOVERY
from mtr_peer_envelope import (
    EnvelopeError, sign_peer_receipt, verify_receipt_query,
)
from mtr_peer_https_pilot import PeerPilotDenied, PeerPilotProtocolError
from tests import test_mtr_e2_host_peer_pilot as fixture_module

CARD = fixture_module.CARD
KEYS = fixture_module.KEYS
PASS = fixture_module.PASS


TARAZ = Path(r"D:\CoS-Test\000- Taraz\taraz-mtr-e2-isolated-20261109")
QUERY_ID = "b" * 32


class JournalHostBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not TARAZ.is_file() and not (TARAZ / "taraz_mtr_peer_registry.py").is_file():
            raise unittest.SkipTest("explicit detached synthetic Taraz source unavailable")
        with patch.dict(os.environ, {"MTR_TARAZ_SOURCE": str(TARAZ)}):
            fixture_module.HostToPeerIntegratedTests.setUpClass()

    def setUp(self):
        self.fx = fixture_module.HostToPeerIntegratedTests(
            "test_current_host_principal_one_shot_signed_roundtrip"
        )
        self.addCleanup(self.fx.doCleanups)
        self.fx.setUp()
        self.digest = self.fx.authorize()
        result = self.fx.send(self.digest)
        self.assertTrue(result["dispatchSlotConsumed"])

    def query(self, *, token=None):
        return self.fx.coordinator.query_first(
            token=token or self.fx.token, task_id=CARD,
            request_id=self.fx.request_id, base_revision=self.fx.revision,
        )

    def rows(self):
        return self.fx.journal.observations(
            principal=self.fx.adapter._recovery_principal(self.fx.token),
            request_id=self.fx.request_id,
            expected_base_revision=self.fx.revision,
            token=self.fx.token,
        )

    def gate_status(self, token):
        issuer = self.fx.coordinator._provenance
        return self.fx.gate.recovery_status(
            principal=self.fx.adapter._recovery_principal(token),
            request_id=self.fx.request_id,
            expected_base_revision=self.fx.revision,
            token=token,
            gate_seal=issuer.issue_recovery(token, audience=GATE_RECOVERY),
            outbox_seal=issuer.issue_recovery(token, audience=OUTBOX_RECOVERY),
        )

    def gate_is_permanently_consumed(self):
        status = self.gate_status(self.fx.token)
        self.assertTrue(status["reservationConsumed"])
        self.assertFalse(status["mayDispatch"])
        with self.assertRaises((DispatchGateConflict, PermissionError)):
            self.fx.send(self.digest)
        with self.fx.registry._connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM requests").fetchone()[0], 1)

    def test_relogin_same_actor_is_scoped_and_cannot_rearm(self):
        token = self.fx.host.authenticate("editor", PASS)["token"]
        self.assertNotEqual(token, self.fx.token)
        observed = self.query(token=token)
        self.assertEqual(observed["lookupStatus"], "received")
        self.assertFalse(observed["officialTarazReceipt"])
        self.assertFalse(observed["financialEventCreated"])
        self.assertFalse(observed["canAutoRetry"])
        self.assertEqual(len(self.rows()), 1)
        self.gate_is_permanently_consumed()

    def test_role_change_same_actor_cannot_replay_original_peer_role(self):
        owner = self.fx.host.authenticate("owner", PASS)["token"]
        self.fx.host.upsert_user(owner, {
            "username": "editor", "role": "admin", "projects": None,
            "displayRole": "superadmin",
        })
        fresh = self.fx.host.authenticate("editor", PASS)["token"]
        # Authorized identity lineage remains the same; Taraz must reject
        # re-signing a stored editor's request with an admin actorRole.
        # The current peer HTTP boundary reports its rejected response body
        # as a protocol-content-type error rather than a clean 409 denial.
        with self.assertRaises((PeerPilotDenied, PeerPilotProtocolError, PermissionError)):
            self.query(token=fresh)
        self.assertEqual(len(self.fx.journal.observations(
            principal=self.fx.adapter._recovery_principal(fresh),
            request_id=self.fx.request_id,
            expected_base_revision=self.fx.revision,
            token=fresh,
        )), 0)
        with self.fx.registry._connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM requests").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM queries").fetchone()[0], 0)
        self.assertFalse(self.gate_status(fresh)["mayDispatch"])

    def test_unsigned_forged_peer_wire_fails_before_journal_and_never_rearms(self):
        def forged(route, wire, *, response_is_envelope):
            self.assertEqual(route, "/mtr/peer/v2/query")
            return b'{"lookupStatus":"received","verified":true}'
        with patch.object(self.fx.client, "_post", side_effect=forged):
            with self.assertRaises(EnvelopeError):
                self.query()
        self.assertEqual(self.rows(), ())
        self.gate_is_permanently_consumed()

    def test_corrupt_authenticated_peer_wire_fails_closed(self):
        original = self.fx.client._post
        def tamper(route, wire, *, response_is_envelope):
            receipt = original(route, wire, response_is_envelope=response_is_envelope)
            self.assertEqual(route, "/mtr/peer/v2/query")
            return receipt[:-1] + b"X"
        with patch.object(self.fx.client, "_post", side_effect=tamper):
            with self.assertRaises(EnvelopeError):
                self.query()
        self.assertEqual(self.rows(), ())
        self.gate_is_permanently_consumed()

    def test_signed_peer_contradiction_same_query_id_is_denied(self):
        # Genuine first peer lookup, then a *synthetically forged with known
        # TEST KEY* contradictory signed answer to the same query.
        with patch("mtr_e2_host_peer_pilot.secrets.token_hex", return_value=QUERY_ID):
            first = self.query()
        self.assertEqual(first["lookupStatus"], "received")
        def contradictory(route, query_wire, *, response_is_envelope):
            self.assertEqual(route, "/mtr/peer/v2/query")
            instant = datetime.now(timezone.utc).replace(microsecond=0)
            query = verify_receipt_query(
                query_wire, secret=KEYS.sender_secret,
                now=instant,
                expected_organization_id=KEYS.organization_id,
                expected_sender_id=KEYS.sender_id,
                expected_key_id=KEYS.sender_key_id,
                allowed_actor_roles=frozenset({"editor"}),
            )
            return sign_peer_receipt(
                query, lookup_status="unknown", sender_id=KEYS.peer_id,
                key_id=KEYS.peer_key_id,
                issued_at=instant,
                expires_at=instant + timedelta(seconds=60),
                secret=KEYS.peer_secret,
            )
        # The signer is synthetic and host verified; this checks conflicting
        # peer claims, not a malicious user's access to a real Taraz signing key.
        with patch.object(self.fx.client, "_post", side_effect=contradictory), patch(
            "mtr_e2_host_peer_pilot.secrets.token_hex", return_value=QUERY_ID
        ):
            with self.assertRaises(QueryJournalConflict):
                self.query()
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.rows()[0]["lookupStatus"], "received")
        self.gate_is_permanently_consumed()

    def test_live_grant_revoked_after_peer_response_before_journal(self):
        original = self.fx.client._post
        owner = self.fx.host.authenticate("owner", PASS)["token"]
        def reply_then_revoke(route, wire, *, response_is_envelope):
            result = original(route, wire, response_is_envelope=response_is_envelope)
            # A real host ACL operation after the network roundtrip but
            # before the journal callback; not a manually forged principal.
            self.fx.host.upsert_user(owner, {
                "username": "editor", "financeEdit": False,
            })
            return result
        with patch.object(self.fx.client, "_post", side_effect=reply_then_revoke):
            with self.assertRaises(PermissionError):
                self.query()
        self.fx.host.upsert_user(owner, {
            "username": "editor", "financeEdit": True,
        })
        self.assertEqual(self.rows(), ())
        self.gate_is_permanently_consumed()

    def test_no_host_lock_is_held_across_peer_io_but_persist_is_host_locked(self):
        original_post = self.fx.client._post
        original_record = self.fx.journal.record
        observed = []
        def outside_host_lock(route, wire, *, response_is_envelope):
            acquired = Event()
            thread = Thread(target=lambda: (
                self._acquire_both(acquired)
            ), daemon=True)
            thread.start()
            thread.join(1.5)
            self.assertFalse(thread.is_alive(), "network held host locks")
            self.assertTrue(acquired.is_set())
            observed.append("peer unlocked")
            return original_post(route, wire, response_is_envelope=response_is_envelope)
        def inside_host_lock(**kwargs):
            # Already executing in the host's callback. Other LAN threads
            # cannot enter both locks until the durable record completes.
            acquired = Event()
            thread = Thread(target=lambda: self._acquire_both(acquired), daemon=True)
            thread.start()
            self.assertFalse(acquired.wait(0.1), "journal persisted without host ACL lock")
            result = original_record(**kwargs)
            observed.append("journal protected")
            return result
        with patch.object(self.fx.client, "_post", side_effect=outside_host_lock), patch.object(
            self.fx.journal, "record", side_effect=inside_host_lock
        ):
            result = self.query()
        self.assertEqual(result["lookupStatus"], "received")
        self.assertEqual(observed, ["peer unlocked", "journal protected"])
        self.assertEqual(len(self.rows()), 1)
        self.gate_is_permanently_consumed()

    def _acquire_both(self, event):
        with self.fx.host.lock, self.fx.bridge._lock:
            event.set()

    def test_concurrent_query_first_calls_complete_without_deadlock(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.query(), range(2)))
        self.assertTrue(all(row["lookupStatus"] == "received" for row in results))
        self.assertEqual(len(self.rows()), 2)
        self.gate_is_permanently_consumed()

    def test_journal_exhaustion_prevents_success_or_second_dispatch(self):
        limited = QueryObservationJournal(
            self.fx.journal.path, outbox=self.fx.outbox, gate=self.fx.gate,
            max_records=1,
        )
        self.fx.journal = limited
        self.fx.coordinator._journal = limited
        first = self.query()
        self.assertEqual(first["lookupStatus"], "received")
        with self.assertRaisesRegex(QueryJournalError, "capacity"):
            self.query()
        self.assertEqual(len(self.rows()), 1)
        with self.fx.registry._connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM requests").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM queries").fetchone()[0], 2)
        self.gate_is_permanently_consumed()


if __name__ == "__main__":
    unittest.main()
