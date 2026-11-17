"""Synthetic-only proposed Taraz journal witness, not an official receipt.

The test signs wire bytes itself with disposable random keys. There is no
production Taraz signer: HMAC agreement is NOT independent ledger provenance.
Only an isolated TemporaryDirectory stores challenges, never live profiles.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import tempfile
import unittest

from mtr_peer_envelope import (
    canonical_json, sign_receipt_query, sign_request, verify_request,
)
from mtr_taraz_finance_witness_verifier import (
    FinanceWitnessAssessment, FinanceWitnessRejected, FinanceWitnessTrust,
    DurableFinanceWitnessChallenges, TarazFinanceWitnessVerifier,
)


_WIRE_DOMAIN = b"MTR-Taraz-finance-journal-witness-v1\x00"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class FinanceWitnessSyntheticTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="mtr-taraz-witness-synthetic-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.path = self.root / "mtr-taraz-finance-witness-queries.sqlite3"
        self.org = "test-organization"
        self.madar_secret = secrets.token_bytes(48)
        self.taraz_secret = secrets.token_bytes(48)
        self.config = FinanceWitnessTrust(
            organization_id=self.org, madar_sender_id="test-madar",
            madar_key_id="test-madar-key", madar_secret=self.madar_secret,
            taraz_finance_issuer_id="test-taraz-journal-issuer",
            taraz_finance_key_id="test-finance-only-key",
            taraz_finance_secret=self.taraz_secret)
        self.store = DurableFinanceWitnessChallenges(self.path)
        self.verifier = TarazFinanceWitnessVerifier(
            config=self.config, challenges=self.store)
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self.req = secrets.token_hex(16)
        self.challenge = secrets.token_hex(16)
        self.company = secrets.token_hex(16)
        self.actor = "mtr-actor-v1-" + secrets.token_hex(32)
        self.task = "task-1"
        self.project = "project-1"
        self.invoice = "invoice-1"
        self.event_id = "issue-1"
        self.journal_id = "J:" + self.event_id
        self.amount = "1500"
        self.revision = 4
        self.ledger_sha = secrets.token_hex(32)
        # Real Madar taraz_exchange._publish_proposal does not sort JSON keys.
        # This intentionally is a noncanonical insertion-order source file.
        self.source = {
            "schema": 1, "source": "madar", "id": self.req,
            "taskId": self.task, "projectId": self.project,
            "title": "Synthetic invoice source",
            "createdUtc": self.now.isoformat(),
            "expenseId": "expense-qa", "amountRial": self.amount,
        }
        self.source_raw = json.dumps(
            self.source, ensure_ascii=False, separators=(",", ":")).encode("utf8")
        self.assertNotEqual(self.source_raw, canonical_json(self.source))
        self.original_payload = {
            "id": self.req, "taskId": self.task, "projectId": self.project,
            "sourceDigest": sha(self.source_raw), "companyId": self.company,
            "actorId": self.actor, "invoiceId": self.invoice,
            "issueEventId": self.event_id, "journalId": self.journal_id,
        }
        self.original = self.make_original()
        verified_original = verify_request(
            self.original, secret=self.madar_secret, now=self.now,
            expected_organization_id=self.org, expected_sender_id="test-madar",
            expected_key_id="test-madar-key", purpose="finance_review_request",
            allowed_actor_roles=frozenset({"editor"}))
        self.query = sign_receipt_query(
            verified_original, query_request_id=self.challenge,
            key_id="test-madar-key", issued_at=self.now,
            expires_at=self.now + timedelta(seconds=90),
            secret=self.madar_secret)
        self.journal = {
            "id": self.journal_id, "eventId": self.event_id,
            "sourceType": "invoice.issue", "sourceId": self.invoice,
            "date": self.now.date().isoformat(), "reversalOf": None,
            "lines": [
                {"accountId": "1200", "debit": 1500, "credit": 0},
                {"accountId": "4000", "debit": 0, "credit": 1500},
            ],
        }
        self.journal_raw = canonical_json(self.journal)
        self.accounting_event = {
            "eventId": self.event_id, "actor": "test-taraz-editor",
            "command": {
                "type": "invoice.issue", "eventId": self.event_id,
                "invoiceId": self.invoice, "postingDate": self.now.date().isoformat(),
            },
            "result": {
                "documentId": self.invoice, "journalId": self.journal_id,
                "total": 1500,
            },
        }
        self.accounting_event_raw = canonical_json(self.accounting_event)
        self.witness = self.make_witness()

    def make_original(self, *, body=None, org=None, key=None):
        return sign_request(
            self.original_payload if body is None else body,
            organization_id=self.org if org is None else org,
            sender_id="test-madar", actor_role="editor",
            key_id="test-madar-key", request_id=self.req,
            purpose="finance_review_request", issued_at=self.now,
            expires_at=self.now + timedelta(seconds=120),
            secret=self.madar_secret if key is None else key,
            authorized=True, explicit_manual_action=True,
        )

    def make_witness(self, *, overrides=None, key=None):
        body = {
            "protocol": "mtr-taraz-journal-witness",
            "version": 1, "algorithm": "HMAC-SHA256",
            "purpose": "invoice-issue-readback",
            "audience": "madar.finance",
            "organizationId": self.org,
            "issuerId": "test-taraz-journal-issuer",
            "keyId": "test-finance-only-key",
            "requestId": self.req, "originalWireSha256": sha(self.original),
            "originalPayloadSha256": sha(canonical_json(self.original_payload)),
            "queryRequestId": self.challenge, "queryWireSha256": sha(self.query),
            "sourceDigest": sha(self.source_raw), "taskId": self.task,
            "projectId": self.project, "madarActorId": self.actor,
            "companyId": self.company, "invoiceId": self.invoice,
            "issueEventId": self.event_id, "journalId": self.journal_id,
            "currency": "RIAL", "amountRial": self.amount,
            "ledgerRevision": self.revision,
            "ledgerStateSha256": self.ledger_sha,
            "journalEventSha256": sha(self.journal_raw),
            "accountingEventSha256": sha(self.accounting_event_raw),
            "journalEventType": "invoice.issue",
            "journalStatus": "posted",
            "issuedUtc": self.now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "expiresUtc": (self.now + timedelta(seconds=60)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        }
        if overrides:
            body.update(overrides)
        mac = hmac.new(
            self.taraz_secret if key is None else key,
            _WIRE_DOMAIN + canonical_json(body), hashlib.sha256).hexdigest()
        return canonical_json({**body, "mac": mac})

    def register(self, *, original=None, query=None, source=None,
                 explicit_manual_action=True, config=None):
        return self.store.register_manual(
            original_wire=self.original if original is None else original,
            query_wire=self.query if query is None else query,
            source_raw=self.source_raw if source is None else source,
            config=self.config if config is None else config,
            now=self.now, explicit_manual_action=explicit_manual_action)

    def inspect(self, *, witness=None, original=None, query=None, source=None,
                journal=None, event=None, ledger_revision=None, ledger_sha=None,
                verifier=None, now=None):
        return (self.verifier if verifier is None else verifier).inspect_and_consume(
            signed_witness=self.witness if witness is None else witness,
            original_wire=self.original if original is None else original,
            query_wire=self.query if query is None else query,
            source_raw=self.source_raw if source is None else source,
            journal_raw=self.journal_raw if journal is None else journal,
            accounting_event_raw=(self.accounting_event_raw if event is None else event),
            ledger_revision=(self.revision if ledger_revision is None else ledger_revision),
            ledger_state_sha256=(self.ledger_sha if ledger_sha is None else ledger_sha),
            now=self.now if now is None else now,
        )

    def test_valid_synthetic_signed_journal_is_never_official_receipt(self):
        self.assertEqual(self.register()["challengeId"], self.challenge)
        observed = self.inspect()
        self.assertIs(type(observed), FinanceWitnessAssessment)
        self.assertEqual(observed.decision,
                         "SIGNED_WITNESS_STRUCTURALLY_VERIFIED_OFFICIAL_ISSUER_UNAVAILABLE")
        self.assertTrue(observed.signedFinanceWitnessCryptographyVerified)
        self.assertTrue(observed.signedJournalEventBound)
        self.assertTrue(observed.oneTimeDurableChallengeConsumed)
        self.assertEqual(observed.companyId, self.company)
        self.assertEqual(observed.ledgerRevisionClaimed, 4)
        for field in (
                "realTarazIssuerAuthenticated", "independentLiveLedgerReadbackVerified",
                "officialFinanceReceiptVerified", "financialEventCreatedByVerifier",
                "safeToRetryFinancialPosting"):
            self.assertFalse(getattr(observed, field), field)

    def test_missing_trust_and_challenge_must_fail_closed(self):
        no_trust = TarazFinanceWitnessVerifier(config=None, challenges=self.store)
        self.assertEqual(self.inspect(verifier=no_trust).decision,
                         "BLOCKED_NO_OPERATOR_FINANCE_TRUST")
        no_challenges = TarazFinanceWitnessVerifier(
            config=self.config, challenges=None)
        self.assertEqual(self.inspect(verifier=no_challenges).decision,
                         "BLOCKED_NO_DURABLE_CHALLENGE")
        # Even a correct signature with no registered host challenge is denied.
        with self.assertRaisesRegex(FinanceWitnessRejected, "unissued"):
            self.inspect()

    def test_restart_persistent_challenge_replay_and_duplicate_registration(self):
        self.register()
        first = self.inspect()
        self.assertTrue(first.oneTimeDurableChallengeConsumed)
        fresh_store = DurableFinanceWitnessChallenges(self.path)
        restarted = TarazFinanceWitnessVerifier(
            config=self.config, challenges=fresh_store)
        with self.assertRaisesRegex(FinanceWitnessRejected, "consumed"):
            self.inspect(verifier=restarted)
        with self.assertRaisesRegex(FinanceWitnessRejected, "replay"):
            self.register()
        with closing(sqlite3.connect(str(self.path))) as connection:
            row = connection.execute(
                "SELECT state,witness_sha FROM challenges WHERE query_id=?",
                (self.challenge,),
            ).fetchone()
        self.assertEqual(row, ("consumed", sha(self.witness)))

    def test_forged_signature_wrong_key_and_legacy_metadata_receipt_refused(self):
        self.register()
        with self.assertRaisesRegex(FinanceWitnessRejected, "signature"):
            self.inspect(witness=self.make_witness(key=secrets.token_bytes(48)))
        with self.assertRaises(FinanceWitnessRejected):
            self.inspect(witness=canonical_json({
                "protocol": "mtr-peer", "purpose": "receipt_lookup_result",
                "lookupStatus": "received", "officialFinanceReceiptVerified": True,
            }))
        self.assertFalse(self.inspect().officialFinanceReceiptVerified)

    def test_tampered_origin_hmac_cross_org_actor_and_signed_digest_denied(self):
        with self.assertRaises(ValueError):
            self.register(original=self.make_original(org="other-tenant"))
        with self.assertRaises(ValueError):
            self.register(original=self.make_original(key=secrets.token_bytes(48)))
        with self.assertRaises(FinanceWitnessRejected):
            self.register(original=self.make_original(body={
                **self.original_payload, "sourceDigest": "f" * 64}))
        with self.assertRaises(FinanceWitnessRejected):
            self.register(source=canonical_json(self.source))
        with self.assertRaises(FinanceWitnessRejected):
            self.register(source=json.dumps({
                **self.source, "officialFinanceReceiptVerified": True
            }, separators=(",", ":")).encode("utf8"))
        self.register()
        with self.assertRaises((ValueError, FinanceWitnessRejected)):
            self.inspect(source=self.source_raw.replace(b"1500", b"1501"))
        with self.assertRaises(FinanceWitnessRejected):
            self.inspect(witness=self.make_witness(
                overrides={"madarActorId": "mtr-actor-v1-" + "a" * 64}))
        self.assertFalse(self.inspect().officialFinanceReceiptVerified)

    def test_all_company_invoice_project_journal_revision_and_amount_fields_bound(self):
        self.register()
        changes = {
            "companyId": secrets.token_hex(16),
            "projectId": "different-project",
            "invoiceId": "different-invoice",
            "issueEventId": "different-issue",
            "journalId": "J:other",
            "sourceDigest": secrets.token_hex(32),
            "currency": "TOMAN",
            "amountRial": "1501",
            "ledgerRevision": 5,
            "ledgerStateSha256": secrets.token_hex(32),
            "journalEventSha256": secrets.token_hex(32),
            "accountingEventSha256": secrets.token_hex(32),
        }
        for key, changed in changes.items():
            with self.subTest(field=key), self.assertRaises(FinanceWitnessRejected):
                self.inspect(witness=self.make_witness(overrides={key: changed}))
        self.assertFalse(self.inspect().officialFinanceReceiptVerified)

    def test_journal_event_mutation_reversal_bad_balance_and_ledger_revision(self):
        self.register()
        for change in (
                {"reversalOf": "some-prior"},
                {"sourceType": "journal.manual"},
                {"sourceId": "other"},
                {"eventId": "other"},
                {"id": "J:other"},
                {"lines": [
                    {"accountId": "1200", "debit": 1500, "credit": 0},
                    {"accountId": "4000", "debit": 0, "credit": 1000},
                ]}):
            with self.subTest(change=change), self.assertRaises(FinanceWitnessRejected):
                self.inspect(journal=canonical_json({**self.journal, **change}))
        with self.assertRaises(FinanceWitnessRejected):
            self.inspect(event=canonical_json({
                **self.accounting_event, "result": {
                    **self.accounting_event["result"], "total": 1499}}))
        with self.assertRaises(FinanceWitnessRejected):
            self.inspect(ledger_revision=5)
        with self.assertRaises(FinanceWitnessRejected):
            self.inspect(ledger_sha="0" * 64)
        self.assertFalse(self.inspect().officialFinanceReceiptVerified)

    def test_witness_freshness_expiry_future_and_denied_manual_flag(self):
        with self.assertRaisesRegex(FinanceWitnessRejected, "manual"):
            self.register(explicit_manual_action=False)
        self.register()
        for change in (
                {"expiresUtc": self.now.strftime("%Y-%m-%dT%H:%M:%SZ")},
                {"expiresUtc": (self.now + timedelta(seconds=200)).strftime(
                    "%Y-%m-%dT%H:%M:%SZ")},
                {"issuedUtc": (self.now + timedelta(seconds=40)).strftime(
                    "%Y-%m-%dT%H:%M:%SZ")},
                {"issuedUtc": (self.now - timedelta(seconds=1)).strftime(
                    "%Y-%m-%dT%H:%M:%SZ")},
                {"expiresUtc": "2026-99-99T10:00:00Z"}):
            with self.subTest(change=change), self.assertRaises(FinanceWitnessRejected):
                self.inspect(witness=self.make_witness(overrides=change))
        with self.assertRaises((ValueError, FinanceWitnessRejected)):
            self.inspect(now=self.now + timedelta(seconds=91))
        self.assertFalse(self.inspect().officialFinanceReceiptVerified)

    def test_query_mismatch_replay_and_wrong_challenge_rejected(self):
        self.register()
        with self.assertRaises(FinanceWitnessRejected):
            self.inspect(witness=self.make_witness(
                overrides={"queryRequestId": secrets.token_hex(16)}))
        with self.assertRaises(FinanceWitnessRejected):
            self.inspect(witness=self.make_witness(
                overrides={"queryWireSha256": "f" * 64}))
        with self.assertRaises(FinanceWitnessRejected):
            self.inspect(witness=self.make_witness(
                overrides={"originalWireSha256": "f" * 64}))
        self.assertFalse(self.inspect().officialFinanceReceiptVerified)

    def test_reject_untrusted_json_oversized_duplicates_and_extra_flags(self):
        self.register()
        with self.assertRaises(FinanceWitnessRejected):
            self.inspect(witness=self.witness + b" ")
        with self.assertRaises(FinanceWitnessRejected):
            self.inspect(witness=self.witness.replace(
                b'"version":1', b'"version":1,"version":1'))
        with self.assertRaises(FinanceWitnessRejected):
            self.inspect(witness=self.witness.replace(
                b'"mac":', b'"officialFinanceReceiptVerified":true,"mac":'))
        with self.assertRaises(FinanceWitnessRejected):
            self.inspect(witness=b"x" * 20000)
        with self.assertRaises(FinanceWitnessRejected):
            self.inspect(journal=self.journal_raw + b" ")
        self.assertFalse(self.inspect().officialFinanceReceiptVerified)

    def test_parallel_witness_verification_only_one_durable_consumer(self):
        self.register()
        def consume(_):
            try:
                return self.inspect().oneTimeDurableChallengeConsumed
            except FinanceWitnessRejected:
                return False
        with ThreadPoolExecutor(max_workers=8) as workers:
            result = list(workers.map(consume, range(8)))
        self.assertEqual(result.count(True), 1)
        self.assertEqual(result.count(False), 7)

    def test_linked_corrupt_and_unsafe_challenge_database_denied(self):
        with self.assertRaises(FinanceWitnessRejected):
            DurableFinanceWitnessChallenges(self.root / "wrong-name.sqlite3")
        link = self.root / "linked"
        try:
            link.symlink_to(self.root, target_is_directory=True)
        except (OSError, NotImplementedError):
            pass
        else:
            with self.assertRaises(FinanceWitnessRejected):
                DurableFinanceWitnessChallenges(
                    link / "mtr-taraz-finance-witness-queries.sqlite3")
        with closing(sqlite3.connect(str(self.path))) as db:
            db.execute("DROP TRIGGER challenges_immutable")
        with self.assertRaisesRegex(FinanceWitnessRejected, "schema"):
            DurableFinanceWitnessChallenges(self.path)

    def test_explicit_operator_trust_keys_no_static_defaults(self):
        self.assertEqual(repr(self.config),
                         "<FinanceWitnessTrust keys redacted>")
        with self.assertRaises(TypeError):
            __import__("pickle").dumps(self.config)
        with self.assertRaises(FinanceWitnessRejected):
            replace(self.config, taraz_finance_secret=self.madar_secret)
        with self.assertRaises(FinanceWitnessRejected):
            replace(self.config, taraz_finance_secret=b"short")
        with self.assertRaises(FinanceWitnessRejected):
            TarazFinanceWitnessVerifier(config={"verified": True}, challenges=self.store)


if __name__ == "__main__":
    unittest.main()
