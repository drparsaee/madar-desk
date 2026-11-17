"""E2 durable peer-query evidence, entirely disposable and offline."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
from dataclasses import replace
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid

from mtr_e2_dispatch_gate import OneShotDispatchGate
from mtr_e2_query_observation_journal import (
    QueryJournalConflict, QueryJournalError, QueryObservationJournal,
)
from mtr_host_request_store import HostRequestStore, TrustedPrincipal
from mtr_host_principal_provenance import (
    HostPrincipalProvenance, OUTBOX_RECOVERY, GATE_RECOVERY,
)
from mtr_account_lineage import principal_actor_id
from tests import test_mtr_host_principal_provenance as provenance_fixture
from mtr_peer_envelope import (
    EnvelopeError, canonical_json, sign_peer_receipt, sign_receipt_query, sign_request,
    verify_receipt_query, verify_request,
)


NOW = datetime(2026, 11, 10, 6, 0, tzinfo=timezone.utc)
ORG = "synthetic-org"
PROJECT = "synthetic-project"
SENDER_SECRET = b"s" * 32
PEER_SECRET = b"p" * 32
SENDER = "synthetic-madar"
SENDER_KEY = "synthetic-madar-v1"
PEER = "synthetic-taraz"
PEER_KEY = "synthetic-taraz-v1"
REV = 12
TOKEN = "synthetic-old-query-session"
FRESH_TOKEN = "synthetic-fresh-query-session"


def principal(**overrides):
    options = {
        "user_id": principal_actor_id({"accountLineage": provenance_fixture.LINEAGE_ALICE}),
        "org_id": ORG, "session_id": hashlib.sha256(TOKEN.encode("ascii")).hexdigest(),
        "role": "editor", "project_ids": frozenset({PROJECT}),
        "permissions": frozenset({"mtr.prepare", "mtr.manual_send", "mtr.read"}),
        "authenticated": True, "session_valid": True, "active": True,
    }
    options.update(overrides)
    return TrustedPrincipal(**options)


class QueryObservationJournalTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="mtr-e2-query-journal-synthetic-")
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.outbox = HostRequestStore(self.root / "host-outbox.sqlite3")
        self.gate = OneShotDispatchGate(self.root / "host-dispatch.sqlite3", self.outbox)
        self.path = self.root / "query-observations.sqlite3"
        self.journal = QueryObservationJournal(self.path, outbox=self.outbox, gate=self.gate)
        self.host = provenance_fixture.MemoryHost()
        self.host.bridge.state["projects"] = [{"id": PROJECT}]
        self.host.users["alice"]["projects"] = [PROJECT]
        self.host.sessions[TOKEN] = "alice"
        self.host.sessions[FRESH_TOKEN] = "alice"
        self.issuer = HostPrincipalProvenance(self.host, org_id=ORG)
        self.outbox.bind_recovery_provenance(self.issuer)
        self.token = TOKEN
        self.actor = principal()
        self.read_actor = replace(self.actor, permissions=frozenset({"mtr.read"}))
        self.original_id = uuid.uuid4().hex
        self._authorize(self.original_id)

    def _authorize(self, request_id, *, actor=None):
        actor = actor or self.actor
        payload = {
            "schema": 1, "source": "madar", "id": request_id,
            "taskId": "synthetic-task", "projectId": PROJECT,
            "title": "synthetic print-work request",
            "createdUtc": "2026-11-10T05:55:00+00:00",
        }
        prepared = self.outbox.prepare_request(
            principal=actor, request_id=request_id, payload=payload,
            base_revision=REV, current_server_revision=REV,
            prepare_key="prepare-" + request_id,
            explicit_manual_action=True,
        )
        self.outbox.manual_send(
            principal=actor, request_id=request_id,
            expected_payload_sha256=prepared["payloadSha256"],
            expected_base_revision=REV, current_server_revision=REV,
            send_key="send-" + request_id, explicit_manual_action=True,
        )
        self.gate.reserve_once(
            principal=actor, request_id=request_id,
            expected_payload_sha256=prepared["payloadSha256"],
            expected_base_revision=REV, current_server_revision=REV,
            send_key="send-" + request_id,
        )
        return payload

    def _signed(self, *, request_id=None, query_id=None, status="received",
                issued=NOW, actor=None):
        actor = actor or self.read_actor
        request_id = request_id or self.original_id
        query_id = query_id or uuid.uuid4().hex
        snapshot = self.outbox.recovery_snapshot(
            principal=actor, request_id=request_id,
            expected_base_revision=REV,
            token=self.token, seal=self.issuer.issue_recovery(
                self.token, audience=OUTBOX_RECOVERY),
        )
        original_wire = sign_request(
            snapshot["payload"], organization_id=ORG, sender_id=SENDER,
            actor_role=actor.role, key_id=SENDER_KEY, request_id=request_id,
            purpose="finance_review_request", issued_at=issued,
            expires_at=issued + timedelta(minutes=3),
            secret=SENDER_SECRET, authorized=True, explicit_manual_action=True,
        )
        original = verify_request(
            original_wire, secret=SENDER_SECRET, now=issued,
            expected_organization_id=ORG, expected_sender_id=SENDER,
            expected_key_id=SENDER_KEY, purpose="finance_review_request",
            allowed_actor_roles=frozenset({actor.role}),
        )
        query_wire = sign_receipt_query(
            original, query_request_id=query_id, key_id=SENDER_KEY,
            issued_at=issued, expires_at=issued + timedelta(minutes=3),
            secret=SENDER_SECRET,
        )
        query = verify_receipt_query(
            query_wire, secret=SENDER_SECRET, now=issued,
            expected_organization_id=ORG, expected_sender_id=SENDER,
            expected_key_id=SENDER_KEY,
            allowed_actor_roles=frozenset({actor.role}),
        )
        peer_wire = sign_peer_receipt(
            query, lookup_status=status, sender_id=PEER, key_id=PEER_KEY,
            issued_at=issued, expires_at=issued + timedelta(minutes=3),
            secret=PEER_SECRET,
        )
        return {
            "principal": actor, "request_id": request_id,
            "expected_base_revision": REV, "original_wire": original_wire,
            "query_wire": query_wire, "peer_receipt_wire": peer_wire,
            "sender_secret": SENDER_SECRET, "peer_secret": PEER_SECRET,
            "now": issued, "sender_id": SENDER, "sender_key_id": SENDER_KEY,
            "peer_id": PEER, "peer_key_id": PEER_KEY,
            "token": self.token,
        }

    def _read(self, **overrides):
        return self.journal.observations(
            principal=overrides.pop("principal", self.read_actor),
            request_id=overrides.pop("request_id", self.original_id),
            expected_base_revision=overrides.pop("expected_base_revision", REV),
            token=overrides.pop("token", self.token),
            **overrides,
        )

    def test_received_persists_after_restart_and_contains_only_metadata(self):
        args = self._signed()
        first = self.journal.record(**args)
        self.assertFalse(first["idempotent"])
        self.assertEqual(first["lookupStatus"], "received")
        self.assertFalse(first["officialTarazReceipt"])
        self.assertFalse(first["canAutoRetry"])
        self.assertFalse(first["financialEventCreated"])
        self.assertEqual(first["originalPayloadSha256"], hashlib.sha256(
            canonical_json(self.outbox.recovery_snapshot(
                principal=self.read_actor, request_id=self.original_id,
                expected_base_revision=REV,
                token=self.token, seal=self.issuer.issue_recovery(
                    self.token, audience=OUTBOX_RECOVERY),
            )["payload"])).hexdigest())
        self.journal = QueryObservationJournal(
            self.path, outbox=self.outbox, gate=self.gate,
        )
        rows = self._read()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["signedPeerEnvelopeSha256"],
                         hashlib.sha256(args["peer_receipt_wire"]).hexdigest())
        with closing(sqlite3.connect(self.path)) as db:
            columns = [row[1] for row in db.execute("PRAGMA table_info(query_observations)")]
            self.assertNotIn("peer_receipt_wire", columns)
            self.assertNotIn("secret", " ".join(columns))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM query_observations").fetchone()[0], 1)

    def test_exact_replay_idempotent_even_if_equivalent_signatures_are_refreshed(self):
        query_id = uuid.uuid4().hex
        first_args = self._signed(query_id=query_id)
        first = self.journal.record(**first_args)
        self.assertTrue(self.journal.record(**first_args)["idempotent"])
        newer = self._signed(query_id=query_id, issued=NOW + timedelta(seconds=30))
        again = self.journal.record(**newer)
        self.assertTrue(again["idempotent"])
        self.assertEqual(again["signedPeerEnvelopeSha256"], first["signedPeerEnvelopeSha256"])
        self.assertEqual(len(self._read()), 1)

    def test_same_query_id_conflicting_signed_status_or_original_is_rejected(self):
        query_id = uuid.uuid4().hex
        self.journal.record(**self._signed(query_id=query_id, status="received"))
        for status in ("unknown", "not_received"):
            with self.subTest(status=status), self.assertRaises(QueryJournalConflict):
                self.journal.record(**self._signed(query_id=query_id, status=status))
        other_request = uuid.uuid4().hex
        self._authorize(other_request)
        with self.assertRaises(QueryJournalConflict):
            self.journal.record(**self._signed(
                request_id=other_request, query_id=query_id,
            ))
        self.assertEqual(len(self._read()), 1)

    def test_same_query_id_same_payload_but_different_signed_peer_is_conflict(self):
        query_id = uuid.uuid4().hex
        known = self._signed(query_id=query_id, status="received")
        self.journal.record(**known)
        verified_query = verify_receipt_query(
            known["query_wire"], secret=SENDER_SECRET, now=NOW,
            expected_organization_id=ORG, expected_sender_id=SENDER,
            expected_key_id=SENDER_KEY,
            allowed_actor_roles=frozenset({"editor"}),
        )
        other_peer_wire = sign_peer_receipt(
            verified_query, lookup_status="received", sender_id="another-peer",
            key_id="another-peer-key", issued_at=NOW,
            expires_at=NOW + timedelta(minutes=3), secret=PEER_SECRET,
        )
        with self.assertRaises(QueryJournalConflict):
            self.journal.record(**{
                **known, "peer_receipt_wire": other_peer_wire,
                "peer_id": "another-peer", "peer_key_id": "another-peer-key",
            })
        self.assertEqual(len(self._read()), 1)

    def test_not_received_is_unknown_metadata_and_never_rearms(self):
        observed = self.journal.record(**self._signed(status="not_received"))
        self.assertEqual(observed["lookupStatus"], "unknown")
        self.assertFalse(observed["canAutoRetry"])
        self.assertEqual(self.gate.recovery_status(
            principal=self.read_actor, request_id=self.original_id,
            expected_base_revision=REV,
            token=self.token,
            gate_seal=self.issuer.issue_recovery(self.token, audience=GATE_RECOVERY),
            outbox_seal=self.issuer.issue_recovery(self.token, audience=OUTBOX_RECOVERY),
        )["reservationConsumed"], True)

    def test_current_actor_session_role_tenant_and_project_are_rechecked(self):
        data = self._signed()
        revoked = (
            principal(user_id="mallory"),
            principal(org_id="other"),
            principal(project_ids=frozenset({"other"})),
            principal(role="viewer"),
            principal(permissions=frozenset()),
            principal(authenticated=False),
            principal(session_valid=False),
            principal(active=False),
        )
        for actor in revoked:
            with self.subTest(actor=actor), self.assertRaises(PermissionError):
                self.journal.record(**{**data, "principal": actor})
        # A newly authenticated session for the SAME actor is still authorized.
        fresh = replace(self.read_actor, session_id=hashlib.sha256(FRESH_TOKEN.encode()).hexdigest())
        self.assertEqual(self.journal.record(
            **{**data, "principal": fresh, "token": FRESH_TOKEN}
        )["lookupStatus"], "received")
        self.assertEqual(len(self._read(principal=fresh, token=FRESH_TOKEN)), 1)

    def test_requires_a_previously_consumed_dispatch_slot(self):
        second_id = uuid.uuid4().hex
        payload = {
            "schema": 1, "source": "madar", "id": second_id,
            "taskId": "synthetic-task", "projectId": PROJECT,
            "title": "synthetic print-work request",
            "createdUtc": "2026-11-10T05:55:00+00:00",
        }
        prepare = self.outbox.prepare_request(
            principal=self.actor, request_id=second_id, payload=payload,
            base_revision=REV, current_server_revision=REV,
            prepare_key="prepare-" + second_id, explicit_manual_action=True,
        )
        self.outbox.manual_send(
            principal=self.actor, request_id=second_id,
            expected_payload_sha256=prepare["payloadSha256"],
            expected_base_revision=REV, current_server_revision=REV,
            send_key="send-" + second_id, explicit_manual_action=True,
        )
        args = self._signed(request_id=second_id)
        with self.assertRaises(KeyError):
            self.journal.record(**args)
        self.assertEqual(len(self._read()), 0)

    def test_invalid_signatures_and_scope_do_not_append(self):
        args = self._signed()
        for changes in (
            {"sender_secret": b"x" * 32},
            {"peer_secret": b"x" * 32},
            {"peer_id": "different-peer"},
            {"peer_key_id": "different-key"},
            {"peer_receipt_wire": args["peer_receipt_wire"][:-1] + b"X"},
            {"query_wire": args["query_wire"][:-1] + b"X"},
            {"original_wire": args["original_wire"][:-1] + b"X"},
        ):
            with self.subTest(change=list(changes)), self.assertRaises(EnvelopeError):
                self.journal.record(**{**args, **changes})
        self.assertEqual(len(self._read()), 0)

    def test_concurrent_replay_one_insert_no_double_event(self):
        args = self._signed()
        with ThreadPoolExecutor(max_workers=12) as pool:
            result = list(pool.map(lambda _: self.journal.record(**args), range(20)))
        self.assertEqual(sum(not row["idempotent"] for row in result), 1)
        self.assertEqual(len(self._read()), 1)

    def test_concurrent_conflicting_signed_answers_choose_exactly_one(self):
        query_id = uuid.uuid4().hex
        first = self._signed(query_id=query_id, status="received")
        conflict = self._signed(query_id=query_id, status="unknown")
        def run(arguments):
            try:
                return self.journal.record(**arguments)["lookupStatus"]
            except QueryJournalConflict:
                return "conflict"
        with ThreadPoolExecutor(max_workers=2) as pool:
            answers = list(pool.map(run, (first, conflict)))
        self.assertEqual(answers.count("conflict"), 1)
        self.assertEqual(len(self._read()), 1)

    def test_sqlite_update_and_delete_triggers_block_dml(self):
        self.journal.record(**self._signed())
        with closing(sqlite3.connect(self.path)) as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE query_observations SET observed_state='unknown'")
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("DELETE FROM query_observations")
        self.assertEqual(len(self._read()), 1)

    def test_tamper_of_row_and_schema_fail_closed_after_restart(self):
        self.journal.record(**self._signed())
        with closing(sqlite3.connect(self.path)) as db:
            trigger = db.execute(
                "SELECT sql FROM sqlite_master WHERE name='immutable_query_observation_update'"
            ).fetchone()[0]
            db.execute("DROP TRIGGER immutable_query_observation_update")
            db.execute(
                "UPDATE query_observations SET observed_state='unknown'"
            )
            db.execute(trigger)
            db.commit()
        with self.assertRaises(QueryJournalError):
            QueryObservationJournal(self.path, outbox=self.outbox, gate=self.gate)
        with self.assertRaises(QueryJournalError):
            self._read()

    def test_erased_last_row_is_detected_by_sqlite_high_water(self):
        self.journal.record(**self._signed())
        with closing(sqlite3.connect(self.path)) as db:
            trigger = db.execute(
                "SELECT sql FROM sqlite_master WHERE name='immutable_query_observation_delete'"
            ).fetchone()[0]
            db.execute("DROP TRIGGER immutable_query_observation_delete")
            db.execute("DELETE FROM query_observations")
            db.execute(trigger)
            db.commit()
        with self.assertRaisesRegex(QueryJournalError, "high-water"):
            self._read()

    def test_missing_immutable_trigger_and_unknown_version_fail_closed(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("DROP TRIGGER immutable_query_observation_delete")
            db.commit()
        with self.assertRaises(QueryJournalError):
            self.journal.record(**self._signed())
        with self.assertRaises(QueryJournalError):
            QueryObservationJournal(self.path, outbox=self.outbox, gate=self.gate)

    def test_bounded_capacity_rejects_new_ids_but_permits_identical_replay(self):
        self.journal = QueryObservationJournal(
            self.path, outbox=self.outbox, gate=self.gate, max_records=2,
        )
        first = self._signed()
        self.journal.record(**first)
        self.journal.record(**self._signed())
        with self.assertRaisesRegex(QueryJournalError, "capacity"):
            self.journal.record(**self._signed())
        self.assertTrue(self.journal.record(**first)["idempotent"])
        self.assertEqual(len(self._read()), 2)

    def test_bounded_reader_and_corrupt_empty_existing_db(self):
        self.assertRaises(QueryJournalError, self._read, limit=0)
        self.assertRaises(QueryJournalError, self._read, limit=101)
        external = self.root / "existing-empty.sqlite3"
        external.touch()
        with self.assertRaises(QueryJournalError):
            QueryObservationJournal(external, outbox=self.outbox, gate=self.gate)


if __name__ == "__main__":
    unittest.main()
