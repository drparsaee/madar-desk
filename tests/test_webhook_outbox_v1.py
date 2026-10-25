"""Deterministic in-memory checks of host-operated, no-network webhook outbox."""

import copy
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import unittest
from unittest.mock import patch

import webhook_outbox_v1 as wh

NOW = "2026-10-21T09:30:00Z"
SECRET = b"distinct-endpoint-key-32bytes-abcde"  # test-only, never journalled
OTHER_SECRET = b"other-destination-key-32bytes-abc"
EVENT = {
    "eventId": "card-event-01", "projectId": "project-1", "cardId": "card-123",
    "kind": "card_moved", "occurredAt": "2026-10-21T09:29:58Z",
}


class FakeHost:
    def __init__(self, statuses=(204,)):
        self.allowed = {("production-hook", "project-1"), ("second-hook", "project-1")}
        self.statuses = list(statuses)
        self.calls = []
        self.secrets = {"production-hook": SECRET, "second-hook": OTHER_SECRET}

    def authorize(self, target, project):
        return (target, project) in self.allowed

    def secret_provider(self, target):
        return self.secrets[target]

    def transport(self, target, body, headers):
        self.calls.append((target, body, dict(headers)))
        next_status = self.statuses.pop(0) if self.statuses else 204
        if isinstance(next_status, Exception):
            raise next_status
        return next_status


def enqueue(events=None, *, state=None, host=None, target="production-hook", now=NOW):
    host = host or FakeHost()
    return wh.enqueue(wh.empty_state() if state is None else state,
                      [copy.deepcopy(EVENT)] if events is None else events,
                      target_id=target, authorize=host.authorize, now=now)


def run(state, host=None, *, now=NOW, **kwargs):
    host = host or FakeHost()
    return wh.run_batch(state, now=now, authorize=host.authorize,
                        secret_provider=host.secret_provider,
                        transport=host.transport, **kwargs)


class WebhookOutboxTests(unittest.TestCase):
    def test_canonical_json_signature_matches_reference_hmac_and_verifies(self):
        host = FakeHost()
        job = enqueue(host=host)["state"]["jobs"][0]
        body = wh.canonical_body(job["event"], job["deliveryId"], NOW)
        same = wh.canonical_body(copy.deepcopy(job["event"]), job["deliveryId"], NOW)
        self.assertEqual(body, same)
        self.assertEqual(body, json.dumps(json.loads(body), sort_keys=True,
                                          ensure_ascii=False, separators=(",", ":")).encode())
        signature = wh.sign_body(body, SECRET)
        reference = "v1=" + hmac.new(SECRET, b"madar.webhook.v1\n" + body,
                                     hashlib.sha256).hexdigest()
        self.assertEqual(signature, reference)
        self.assertTrue(wh.verify_signature(body, signature, SECRET, now=NOW))
        self.assertFalse(wh.verify_signature(body, signature, OTHER_SECRET, now=NOW))
        self.assertFalse(wh.verify_signature(body + b" ", signature, SECRET, now=NOW))
        self.assertFalse(wh.verify_signature(body, "v1=" + "0" * 64, SECRET, now=NOW))

    def test_signed_body_mutation_duplicate_keys_noncanonical_and_freshness_rejected(self):
        job = enqueue()["state"]["jobs"][0]
        body = wh.canonical_body(job["event"], job["deliveryId"], NOW)
        signature = wh.sign_body(body, SECRET)
        obj = json.loads(body)
        obj["event"]["kind"] = "label_changed"
        changed = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
        self.assertFalse(wh.verify_signature(changed, signature, SECRET, now=NOW))
        self.assertFalse(wh.verify_signature(body, signature, SECRET, now="2026-10-21T09:40:00Z"))
        self.assertTrue(wh.verify_signature(body, signature, SECRET,
                                            now="2026-10-21T09:35:00Z"))
        self.assertFalse(wh.verify_signature(body.replace(b'"event":{', b'"event":{}, "event":{'),
                                             signature, SECRET))
        self.assertFalse(wh.verify_signature(body, signature.upper(), SECRET))
        with self.assertRaises(ValueError):
            wh.sign_body(b"{}", SECRET)
        with self.assertRaises(ValueError):
            wh.verify_signature(body, signature, b"short")

    def test_full_delivery_receipts_audit_and_no_secret_persistence(self):
        host = FakeHost()
        initial = wh.empty_state()
        queued = enqueue(host=host, state=initial)
        self.assertEqual(initial, wh.empty_state())
        self.assertEqual(queued["added"], 1)
        job = queued["state"]["jobs"][0]
        delivered = run(queued["state"], host)
        self.assertEqual(delivered["processed"], 1)
        self.assertEqual(delivered["delivered"], 1)
        self.assertEqual(delivered["state"]["jobs"], [])
        self.assertEqual(delivered["state"]["receipts"][job["deliveryId"]]["statusCode"], 204)
        self.assertEqual([a["outcome"] for a in delivered["state"]["audit"]],
                         ["queued", "delivered"])
        self.assertEqual([a["sequence"] for a in delivered["state"]["audit"]], [1, 2])
        target, body, headers = host.calls[0]
        self.assertEqual(target, "production-hook")
        self.assertEqual(headers["X-Madar-Delivery-Id"], job["deliveryId"])
        self.assertTrue(wh.verify_signature(body, headers["X-Madar-Signature"],
                                            SECRET, now=headers["X-Madar-Sent-At"]))
        self.assertEqual(set(json.loads(body)["event"]),
                         {"eventId", "projectId", "cardId", "kind", "occurredAt"})
        serialized = json.dumps(delivered["state"])
        self.assertNotIn(SECRET.decode(), serialized)
        self.assertNotIn("https://", serialized)
        self.assertNotIn("X-Madar-Signature", serialized)
        self.assertTrue(wh.validate_state(json.loads(serialized)))

    def test_duplicate_enqueue_pending_then_delivered_survives_json_restart(self):
        host = FakeHost()
        pending = enqueue(host=host)["state"]
        restarted = json.loads(json.dumps(pending))
        identical = enqueue(state=restarted, host=host)
        self.assertEqual(identical["added"], 0)
        self.assertEqual(identical["duplicates"], 1)
        self.assertEqual(len(identical["state"]["audit"]), 1)
        delivered = run(restarted, host)["state"]
        cold_start = json.loads(json.dumps(delivered))
        self.assertEqual(enqueue(state=cold_start, host=host)["added"], 0)
        self.assertEqual(run(cold_start, host)["processed"], 0)
        self.assertEqual(len(host.calls), 1)
        mutated = {**EVENT, "kind": "card_created"}
        with self.assertRaisesRegex(ValueError, "reused"):
            enqueue([mutated], state=cold_start, host=host)

    def test_distinct_destinations_have_distinct_deterministic_delivery_ids(self):
        first = enqueue()["state"]
        second = enqueue(state=first, target="second-hook")["state"]
        self.assertEqual(len(second["jobs"]), 2)
        self.assertNotEqual(second["jobs"][0]["deliveryId"], second["jobs"][1]["deliveryId"])
        self.assertEqual({item["targetId"] for item in second["jobs"]},
                         {"production-hook", "second-hook"})
        self.assertEqual([r["outcome"] for r in second["audit"]], ["queued", "queued"])

    def test_untrusted_payload_injection_finance_and_security_events_rejected(self):
        attempts = [
            {**EVENT, "kind": "finance.invoice.created"},
            {**EVENT, "kind": "security.password_reset"},
            {**EVENT, "kind": "custom_field_changed"},
            {**EVENT, "title": "Client contract private"},
            {**EVENT, "data": {"bankAccount": "SENSITIVE"}},
            {**EVENT, "url": "https://127.0.0.1/admin"},
            {**EVENT, "secret": SECRET.decode()},
            {**EVENT, "eventId": "event-1\nInjected: header"},
            {**EVENT, "projectId": "http://169.254.169.254/"},
            {**EVENT, "occurredAt": "2026-10-21"},
            {**EVENT, "occurredAt": None},
            {**EVENT, "kind": ["card_created"]},
            {**EVENT, "cardId": 123},
            None, {}, [],
        ]
        empty = wh.empty_state()
        for data in attempts:
            with self.subTest(case=str(data)[:55]), self.assertRaises(ValueError):
                enqueue([data], state=empty)
            self.assertEqual(empty, wh.empty_state())

    def test_destination_scopes_revocation_and_bad_authorizer_are_denied(self):
        host = FakeHost()
        with self.assertRaises(PermissionError):
            enqueue([EVENT], host=host, target="unconfigured")
        with self.assertRaises(PermissionError):
            enqueue([{**EVENT, "projectId": "private-project"}], host=host)
        with self.assertRaises(ValueError):
            wh.enqueue(wh.empty_state(), [EVENT], target_id="production-hook",
                       authorize=lambda *_: 1, now=NOW)
        state = enqueue(host=host)["state"]
        host.allowed.clear()
        result = run(state, host)
        self.assertEqual(result["dead"], 1)
        self.assertEqual(result["state"]["jobs"][0]["lastError"], "destination_revoked")
        self.assertEqual(host.calls, [])
        with self.assertRaises(PermissionError):
            enqueue([EVENT], state=result["state"], host=host)
        # Reject unsafe endpoint-looking strings, even when host policy is broad.
        for destination in ("https:evil", "127.0.0.1", "http://localhost",
                            "internal/path", "webhook.example", "a\nB"):
            with self.subTest(destination=destination), self.assertRaises(ValueError):
                enqueue([EVENT], host=host, target=destination)

    def test_retryable_http_status_and_increasing_backoff_without_early_retry(self):
        host = FakeHost([503, 429, 204])
        pending = enqueue(host=host)["state"]
        first = run(pending, host)
        self.assertEqual(first["retried"], 1)
        self.assertEqual(first["state"]["jobs"][0]["nextAttemptAt"],
                         "2026-10-21T09:31:00.000000Z")
        early = run(first["state"], host, now="2026-10-21T09:30:30Z")
        self.assertEqual(early["processed"], 0)
        second = run(first["state"], host, now="2026-10-21T09:31:00Z")
        self.assertEqual(second["retried"], 1)
        self.assertEqual(second["state"]["jobs"][0]["attempts"], 2)
        self.assertEqual(second["state"]["jobs"][0]["nextAttemptAt"],
                         "2026-10-21T09:33:00.000000Z")
        third = run(second["state"], host, now="2026-10-21T09:33:00Z")
        self.assertEqual(third["delivered"], 1)
        self.assertEqual(len(host.calls), 3)
        self.assertEqual([record["outcome"] for record in third["state"]["audit"]],
                         ["queued", "retry", "retry", "delivered"])
        self.assertEqual({json.loads(call[1])["deliveryId"] for call in host.calls},
                         set(third["state"]["receipts"]))

    def test_network_exceptions_retry_dead_and_explicit_admin_requeue(self):
        host = FakeHost([TimeoutError("private URL"), ConnectionError("timeout"), 204])
        pending = enqueue(host=host)["state"]
        first = run(pending, host, max_attempts=2)
        self.assertEqual(first["retried"], 1)
        second = run(first["state"], host, max_attempts=2, now="2026-10-21T09:31:00Z")
        self.assertEqual(second["dead"], 1)
        self.assertEqual(second["state"]["jobs"][0]["status"], "dead")
        self.assertNotIn("private URL", json.dumps(second["state"]))
        self.assertEqual(run(second["state"], host)["processed"], 0)
        delivery_id = second["state"]["jobs"][0]["deliveryId"]
        requeued = wh.requeue_dead(second["state"], delivery_id, now="2026-10-21T09:32:00Z")
        self.assertEqual(requeued["jobs"][0]["attempts"], 0)
        self.assertEqual(requeued["audit"][-1]["outcome"], "requeued")
        self.assertEqual(run(requeued, host, now="2026-10-21T09:32:00Z")["delivered"], 1)
        self.assertEqual(second["state"]["jobs"][0]["status"], "dead")

    def test_permanent_status_credential_missing_and_unexpected_status(self):
        blocked = FakeHost([403])
        self.assertEqual(run(enqueue(host=blocked)["state"], blocked)["dead"], 1)
        no_secret = FakeHost()
        no_secret.secrets.clear()
        output = run(enqueue(host=no_secret)["state"], no_secret)
        self.assertEqual(output["dead"], 1)
        self.assertEqual(output["state"]["jobs"][0]["lastError"], "secret_unavailable")
        self.assertEqual(no_secret.calls, [])
        bizarre = FakeHost(["200", 204])
        first = run(enqueue(host=bizarre)["state"], bizarre)
        self.assertEqual(first["retried"], 1)
        self.assertEqual(first["state"]["jobs"][0]["lastError"], "unexpected_status")

    def test_offline_flag_never_signs_or_invokes_network_callbacks(self):
        host = FakeHost()
        state = enqueue(host=host)["state"]
        offline = run(state, host, offline=True)
        self.assertEqual(offline["processed"], 0)
        self.assertEqual(offline["state"], state)
        self.assertEqual(host.calls, [])
        self.assertEqual(run(json.loads(json.dumps(state)), host)["delivered"], 1)

    def test_invalid_journal_and_secret_injection_fail_before_any_send(self):
        original = enqueue()["state"]
        corrupted = [
            lambda s: s["jobs"][0].update(targetId="https://user:pass@host/path"),
            lambda s: s["jobs"][0].update(deliveryId="wh-" + "0" * 40),
            lambda s: s["jobs"][0].update(fingerprint="0" * 64),
            lambda s: s["jobs"][0].update(status="delivered"),
            lambda s: s["jobs"][0].update(status=[]),
            lambda s: s["jobs"][0].update(secret=SECRET.decode()),
            lambda s: s["audit"][0].update(sequence=9),
            lambda s: s["audit"][0].update(errorCode="C:\\secret"),
            lambda s: s.update(nextAudit=False),
            lambda s: s.update(untrustedUrl="http://localhost"),
        ]
        for change in corrupted:
            candidate = copy.deepcopy(original)
            change(candidate)
            with self.subTest(change=change), self.assertRaises(ValueError):
                run(candidate)
        self.assertTrue(wh.validate_state(original))
        self.assertEqual(original["jobs"][0]["attempts"], 0)

    def test_queue_batch_size_maximum_and_run_batch_limits(self):
        host = FakeHost()
        events = [{**EVENT, "eventId": f"e-{i}"} for i in range(100)]
        state = enqueue(events, host=host)["state"]
        self.assertEqual(len(state["jobs"]), 100)
        first = run(state, host, limit=7)
        self.assertEqual(first["processed"], 7)
        self.assertEqual(len(first["state"]["receipts"]), 7)
        for bad in (False, 0, 26, -1, 0.5):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                run(state, host, limit=bad)
        with self.assertRaises(ValueError):
            enqueue(events + [EVENT], host=host)
        self.assertEqual(wh.MAX_QUEUE, 500)

    def test_no_external_calls_if_audit_or_receipt_capacity_is_exhausted(self):
        host = FakeHost()
        pending = enqueue(host=host)["state"]
        with patch.object(wh, "MAX_RECEIPTS", 0):
            with self.assertRaisesRegex(ValueError, "receipt capacity"):
                run(pending, host)
        with patch.object(wh, "MAX_AUDIT", 1):
            with self.assertRaisesRegex(ValueError, "audit capacity"):
                run(pending, host)
        self.assertEqual(host.calls, [])
        self.assertEqual(len(pending["jobs"]), 1)

    def test_tampered_pending_journal_cannot_redirect_to_different_target(self):
        pending = enqueue()["state"]
        mutated = copy.deepcopy(pending)
        mutated["jobs"][0]["targetId"] = "second-hook"
        with self.assertRaises(ValueError):
            run(mutated)
        mutated = copy.deepcopy(pending)
        mutated["jobs"][0]["event"]["cardId"] = "private-card"
        with self.assertRaises(ValueError):
            run(mutated)

    def test_transport_idempotency_boundary_after_receiver_ack_before_host_commit(self):
        host = FakeHost()
        pending = enqueue(host=host)["state"]
        delivered = run(pending, host)
        self.assertEqual(delivered["delivered"], 1)
        # Simulate a process crash AFTER accepted transport but BEFORE state
        # CAS is committed, so durable store still contains pending journal.
        stale = json.loads(json.dumps(pending))
        replayed = run(stale, host)
        self.assertEqual(replayed["delivered"], 1)
        self.assertEqual(len(host.calls), 2)
        self.assertEqual(host.calls[0][2]["X-Madar-Delivery-Id"],
                         host.calls[1][2]["X-Madar-Delivery-Id"])
        self.assertNotEqual(delivered["state"]["nextAudit"], pending["nextAudit"])
        # Receiver MUST deduplicate deliveryId; engine cannot guarantee
        # external exactly-once semantics without receiver cooperation.


if __name__ == "__main__":
    unittest.main()
