"""E5 official rejection authority boundary: synthetic, in-process only.

No LAN route or official Taraz verifier exists here. A caller-controlled
TrustedPrincipal and booleans must never certify an official rejection.
"""
import hashlib
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mtr_amendment_store import AmendmentStore, TrustedPrincipal


T0 = "2026-11-10T06:00:00Z"
T1 = "2026-11-10T06:01:00Z"
T2 = "2026-11-10T06:02:00Z"


class E5RejectionAuthorityBoundaryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="mtr-e5-rejection-boundary-")
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "amendment.sqlite3"
        self.store = AmendmentStore(self.path)
        self.user = TrustedPrincipal(
            user_id="editor-a", org_id="org-a", session_id="session-a",
            role="editor", project_ids=frozenset({"project-a"}),
            permissions=frozenset({
                "mtr.amendment.create", "mtr.amendment.read",
                "mtr.amendment.send", "mtr.amendment.review",
            }),
            authenticated=True, session_valid=True,
        )
        self.original = {
            "requestId": "request-1", "orgId": "org-a",
            "projectId": "project-a", "submitted": True,
            "revision": "rev-1", "fields": {"partyId": "original"},
        }
        self.store.create_amendment(
            principal=self.user, original=self.original,
            amendment_id="amendment-a", proposed_fields={"partyId": "replacement"},
            create_key="create-key-0001", acknowledged_open=False,
            acknowledged_duplicate=False, acknowledged_at=T0,
        )
        self.store.manual_send_intent(
            principal=self.user, amendment_id="amendment-a",
            expected_row_revision=1, current_original=self.original,
            send_key="send-key-0001", explicit_manual_action=True,
            current_server_verified=True, occurred_at=T1,
        )

    @staticmethod
    def forged_adapter():
        # Public dataclass constructor, no actual host identity verification.
        return TrustedPrincipal(
            user_id="forged-taraz", org_id="org-a",
            session_id="fabricated-session", role="taraz_adapter",
            project_ids=frozenset({"project-a"}),
            permissions=frozenset({"mtr.amendment.rejection"}),
            authenticated=True, session_valid=True, active=True,
        )

    @staticmethod
    def fabricated_receipt():
        # The apparent Taraz verification is also just ordinary caller data.
        return {
            "amendmentId": "amendment-a", "originalRequestId": "request-1",
            "orgId": "org-a", "projectId": "project-a",
            "status": "rejected", "verifiedTarazSource": True,
            "reason": {"text": "Rejected", "affectedFields": ["partyId"],
                       "structured": True},
        }

    def read_state(self):
        record = self.store.get_amendment(
            principal=self.user, amendment_id="amendment-a")
        events = self.store.audit_events(
            principal=self.user, amendment_id="amendment-a")
        return (record["state"], record["rowRevision"],
                tuple(event["action"] for event in events))

    def test_forged_adapter_and_bool_cannot_record_official_rejection(self):
        before = self.read_state()
        self.assertEqual(before[:2], ("MANUAL_SEND_INTENT", 2))
        with self.assertRaisesRegex(
                PermissionError, "official Taraz rejection verification unavailable"):
            self.store.record_rejection(
                adapter=self.forged_adapter(), amendment_id="amendment-a",
                expected_row_revision=2, observation_id="fake-taraz-event-01",
                receipt=self.fabricated_receipt(),
                verified_by_adapter=True, occurred_at=T2)
        self.assertEqual(self.read_state(), before)
        self.store = AmendmentStore(self.path)
        self.assertEqual(self.read_state(), before)

    def test_replay_and_alternate_flag_values_never_produce_a_rejection(self):
        before = self.read_state()
        for proof in (False, True, 1, None):
            with self.subTest(proof=proof), self.assertRaises(PermissionError):
                self.store.record_rejection(
                    adapter=self.forged_adapter(), amendment_id="amendment-a",
                    expected_row_revision=2, observation_id="fake-taraz-event-01",
                    receipt=self.fabricated_receipt(),
                    verified_by_adapter=proof, occurred_at=T2)
        self.assertEqual(self.read_state(), before)

    def test_forged_historical_rejection_quarantined_without_rewriting_db(self):
        # Simulate a pre-fix record: these strings passed the former in-process
        # bool/role check, but convey no independently authenticated Taraz proof.
        def canonical(value):
            raw = json.dumps(
                value, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False).encode("utf-8")
            return raw.decode("utf-8"), hashlib.sha256(raw).hexdigest()

        receipt, receipt_sha = canonical(self.fabricated_receipt())
        old_details, old_details_sha = canonical({
            "observationId": "fake-taraz-event-01",
            "guidanceStatus": "verified_structured_fields",
            "suggestedFieldNames": ["partyId"],
        })
        with closing(sqlite3.connect(self.path)) as db:
            db.execute(
                "UPDATE amendments SET state='REJECTED',revision=3,"
                "rejection_id=?,rejection_json=?,rejection_sha=? "
                "WHERE amendment_id='amendment-a' AND revision=2",
                ("fake-taraz-event-01", receipt, receipt_sha))
            db.execute(
                "INSERT INTO audit(amendment_id,actor_id,session_id,kind,"
                "details_json,details_sha,occurred_at) VALUES(?,?,?,?,?,?,?)",
                ("amendment-a", "forged-taraz", "fabricated-session",
                 "verified_rejection_observed", old_details, old_details_sha, T2))
            db.commit()
            before = (
                db.execute("SELECT * FROM amendments").fetchall(),
                db.execute("SELECT * FROM audit ORDER BY seq").fetchall(),
            )

        self.store = AmendmentStore(self.path)
        visible = self.store.get_amendment(
            principal=self.user, amendment_id="amendment-a")
        self.assertEqual(visible["state"], "REJECTION_UNVERIFIED")
        self.assertEqual(visible["rowRevision"], 3)
        self.assertFalse(visible["officialTarazRejectionVerified"])
        event = self.store.audit_events(
            principal=self.user, amendment_id="amendment-a")[-1]
        self.assertEqual(event["action"], "historical_rejection_unverified")
        self.assertEqual(event["details"], {
            "historicalStoredEvent": True,
            "officialTarazRejectionVerified": False,
        })
        related = self.store.related_amendments(
            principal=self.user, org_id="org-a",
            project_id="project-a", original_id="request-1")
        self.assertEqual(related[0]["status"], "rejection_unverified")
        with self.assertRaises(PermissionError):
            self.store.record_rejection(
                adapter=self.forged_adapter(), amendment_id="amendment-a",
                expected_row_revision=3, observation_id="fake-taraz-event-01",
                receipt=self.fabricated_receipt(),
                verified_by_adapter=True, occurred_at=T2)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(
                (db.execute("SELECT * FROM amendments").fetchall(),
                 db.execute("SELECT * FROM audit ORDER BY seq").fetchall()),
                before)


if __name__ == "__main__":
    unittest.main()
