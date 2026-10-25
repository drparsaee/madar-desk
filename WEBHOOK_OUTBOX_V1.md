# Madar Desk 1.0: signed webhook outbox

## Status: OUTBOX ONLY, NO LIVE WEBHOOK TRANSPORT

webhook_outbox_v1.py is a pure in-memory bounded queue and HMAC signer.
It does **not** open URLs, sockets, DNS, files, APPDATA, schedulers or HTTP
connections. Live outbound webhooks, user configuration, LAN/native bridges,
UI and TLS/SSRF defenses have NOT been installed or tested. An authorized host
can provide callbacks after integrating durable persistence and networking.

Owned new files: webhook_outbox_v1.py, tests/test_webhook_outbox_v1.py,
WEBHOOK_OUTBOX_V1.md. No other files have been edited.

## Only allowed event data

Every event MUST be a JSON object with exactly five fields:

    {
      "eventId": "card-event-01",
      "projectId": "project-1",
      "cardId": "card-17",
      "kind": "card_moved",
      "occurredAt": "2026-10-21T09:30:00Z"
    }

The only allowed kinds are card_created, card_moved, label_changed and
checklist_completed. All IDs and timestamps are strictly validated. No
free-form text or other data can be added: in particular reject card title,
description, comments, user identity, custom field values, event data,
attachments, finance, bank, customer, invoices, passwords, secrets,
access control and security events. IDs can still be sensitive.

The host should project only eventId, cardId and kind/trigger from its
authorized automation_events.card_change_events result. The projectId must
be obtained from a trusted card lookup and occurredAt from the authenticated
commit timestamp. Explicitly drop command data, and exclude any
custom_field_changed event. Check project/actor/destination ACL first.

## Public API and host-owned callbacks

    import webhook_outbox_v1 as wh

    def authorize(target_id, project_id):
        # Host-only: target enabled and authorized for project?
        return (target_id, project_id) in trusted_scopes

    def secret_provider(target_id):
        # Host-only: 32..256 byte secret, never journal-persisted
        return trusted_secret_store[target_id]

    def transport(target_id, body_bytes, headers):
        # NOT PROVIDED HERE: host-only approved HTTPS sender.
        # Resolve opaque ID through trusted destination configuration.
        return approved_sender(target_id, body_bytes, headers)

    state = wh.empty_state()
    queued = wh.enqueue(
        state, [event], target_id="production-hook",
        authorize=authorize, now="2026-10-21T09:30:00Z",
    )
    state = queued["state"]  # added, duplicates
    # Commit state durably through host CAS BEFORE accepting the event.

    result = wh.run_batch(
        state, now="2026-10-21T09:31:00Z",
        authorize=authorize, secret_provider=secret_provider,
        transport=transport, limit=10, max_attempts=5, offline=False,
    )
    state = result["state"]  # processed, delivered, retried, dead
    # Commit state durably with exclusive/CAS host persistence.

    # ADMIN-ONLY: state = wh.requeue_dead(state, delivery_id, now=timestamp)

Callbacks have strict signatures:

* authorize(target_id, project_id) returns actual bool, evaluated at
  enqueue AND on every dispatch. Revocation dead-letters without transport.
* secret_provider(target_id) returns bytes with length 32..256, read only
  from host-only secret storage. Missing/invalid secret dead-letters.
* transport(target_id, body_bytes, headers) returns int HTTP status
  (100..599). Actual host transport maps an opaque target ID to an
  administrator-approved endpoint. The outbox never receives a URL.
  Successful 2xx creates a durable receipt; 408/425/429/5xx or OSError
  retries; other 4xx permanently dead-letter. Unexpected status retries.
  Host should convert ordinary network failures to OSError and bound timeout.

Target IDs are opaque up to 64 ASCII characters, strictly alphanumeric
plus underscore/hyphen: no URL schemes, colons, dots, slashes or hostnames.
No destination URL is stored in a job or passed to the outbox engine.

### Required transport security before enabling live delivery

An actual host-supplied transport MUST accept only preapproved HTTPS
destinations; verify TLS, prohibit arbitrary redirects or HTTP downgrade,
credentials in URLs, private/loopback/link-local/metadata IPs, DNS rebinding,
proxy bypass, unsupported ports, uncontrolled request/response bodies and
unbounded timeouts. Validate/pin destination and resolved address on every
dispatch. NONE of these live network controls are implemented by this
module because it deliberately does no network I/O.

## HMAC canonical delivery contract

Outgoing body is compact UTF-8 JSON with sorted keys, no whitespace,
NaN/Infinity, duplicate keys or arbitrary fields. The complete signed
object contains: schemaVersion=1, deliveryId, sentAt and event (the exact
minimal five-field object above).

    deliveryId = "wh-" + SHA256(canonical_json([target_id, eventId]))[:40 hex]
    exact_bytes = JSON.stringify_sorted_compact({
        "schemaVersion": 1,
        "deliveryId": deliveryId,
        "sentAt": delivery_time,
        "event": minimal_event
    }).encode("utf-8")
    signature = "v1=" + hex(HMAC_SHA256(
        destination_secret,
        b"madar.webhook.v1\n" + exact_bytes
    ))

Transport headers:

    Content-Type: application/json
    X-Madar-Signature: v1=<64 lowercase hex characters>
    X-Madar-Delivery-Id: wh-<40 lowercase hex characters>
    X-Madar-Sent-At: <offset-aware ISO timestamp>

wh.sign_body(body, secret) emits the signature; wh.verify_signature(body,
signature, secret, now=timestamp, max_age_seconds=300) checks canonical
JSON, constant-time HMAC and optional send-time freshness. The helper
DOES NOT itself perform receiver ACL, ingress authentication or persist a
replay cache. The receiving service MUST validate the endpoint/key,
project scope and matching deliveryId header, and durably deduplicate
deliveryId. A valid signature and timestamp are insufficient to prevent
duplicate processing. sentAt and HMAC may change on retry; deliveryId
remains identical.

## Journal / retry / idempotency contract

    {
      "schemaVersion": 1, "jobs": [], "receipts": {},
      "audit": [], "nextAudit": 1
    }

Job fields are strictly allowlisted: deliveryId, targetId, event,
fingerprint, status, attempts, queuedAt, nextAttemptAt and lastError.
Audit contains sequence, deliveryId, outcome, attempt, errorCode, at.
Successful receipts contain fingerprint, time and 2xx statusCode.
No credentials, secrets, URLs, signed bytes, request/response headers,
response bodies or raw exception texts are persisted. All errors in
the journal are normalized non-sensitive codes.

The tuple (targetId, eventId) always yields the same deliveryId. Re-enqueue
of identical payload is a no-op across JSON restart or after delivery;
re-enqueue of different payload under the same key is rejected. One event
can be independently queued to different authorized destinations.

Retry is exponential 60,120,240,... seconds, max 3600s. The retry budget
may be set to 1..8 attempts. Dead letters remain until explicitly requeued
by an administrator through a CAS journal transaction. Queue is bounded
to 500 jobs, 100 events per enqueue, 25 deliveries per batch, 5000 audit
entries, 5000 receipts, 4 MB journal, and 2048-byte signed request.
Capacity exhaustion fails closed; receipts are not auto-pruned because
doing so weakens deduplication. offline=True does no callback work.

EXTERNAL DELIVERY IS AT-LEAST-ONCE, NOT EXACTLY-ONCE. If an HTTP 2xx is
received but the process dies before its receipt is committed locally,
the same deliveryId can be retransmitted. The test simulates this exact
crash window. Recipient-side idempotency is mandatory.

### Prime integration boundaries

webhook_outbox_v1.py is NOT wired to native_app.py, lan.py, UI,
the existing task/automation journal or an EXE. Current UnifiedAppStorage
supports the fixed four/five-domain schema for task/collab/finance/
completion_outbox/automation and DOES NOT persist this new webhook journal.
Prime must deliberately design host-only durable storage and CAS handling,
or coordinate a separate migration. Never add unvalidated extra fields to
other domains. Prefer atomic task-change/event enqueue commits. Serialize
read/run_batch/commit; on conflict reload/reconcile. Host authorization
MUST use trusted session/project scopes; raw client events must not be
accepted as preauthorized. Do not enable live sends before endpoint security
and receiver deduplication have been reviewed.

## Exact tests

    python -m unittest discover -s tests -p test_webhook_outbox_v1.py -v
    python -m py_compile webhook_outbox_v1.py tests/test_webhook_outbox_v1.py

Deterministic in-memory tests use only fake callback transports with no
network or real APPDATA. Coverage: HMAC reference vector; canonical JSON;
wrong-secret, mutated/noncanonical/duplicate-JSON or stale-signature
rejection; finance/security/URL/data injection refusal; malformed or poisoned
journal rejection; destination/project ACL and revocation; restart, replay,
payload collisions and multiple destinations; 2xx receipt/audit; 503/429
backoff; OSError timeout; dead letter/requeue; missing key; bounds and
preflight capacity; offline skips; remote-ack-before-local-commit duplicate.

Live TLS/SSRF/HTTP functionality and end-to-end webhooks: NOT IMPLEMENTED
OR TESTED. This is a security-conscious isolated outbox, nothing more.

## Verification results (worker-3)

    python -m unittest discover -s tests -p test_webhook_outbox_v1.py -v
    # 16 tests: PASS=16, FAIL=0, ERROR=0, exit=0

    python -m unittest discover -s tests -p test_automation_v1.py -v
    # 14 regression tests: PASS=14, FAIL=0, ERROR=0, exit=0

    python -m unittest discover -s tests -p test_automation_storage.py -v
    # 12 regression tests: PASS=12, FAIL=0, ERROR=0, exit=0

    python -m py_compile webhook_outbox_v1.py tests/test_webhook_outbox_v1.py
    # PASS, exit=0

In total, 42 directly executed Python tests passed. The existing npm/full
release test suite and EXE GUI smoke are Prime-owned and were NOT run by this
worker. These results verify a pure callback contract, not live HTTP delivery.
