# MTR E2: SQLite host outbox pilot | 2026-11-09

**Status: isolated, unit-tested metadata-only implementation.**
This is NOT an operational Madar-LanService integration, Taraz transport,
official finance workflow, posting engine, or deployment.

Source: mtr_host_request_store.py
Tests: tests/test_mtr_host_request_store.py (synthetic TemporaryDirectory only)

## Public API

HostRequestStore(path: pathlib.Path) requires an absolute .sqlite3 path in
an existing trusted OS-ACL-protected directory chosen by the host. It creates
only the independent metadata tables requests, observations and audit, and
rejects unknown schema versions and unsafe paths. Do not accept a client
supplied arbitrary path.

Methods and keyword-only arguments:

    prepare_request(principal, request_id, payload, base_revision,
                    current_server_revision, prepare_key,
                    explicit_manual_action) -> dict

    manual_send(principal, request_id, expected_payload_sha256,
                expected_base_revision, current_server_revision, send_key,
                explicit_manual_action) -> dict

    record_query_result(principal, request_id, evidence,
                        verified_by_adapter) -> dict

    receipt_status(principal, request_id, expected_base_revision) -> dict
    request_snapshot(principal, request_id, expected_base_revision) -> dict
    audit_events(principal, request_id, expected_base_revision) -> tuple
    backup_to(destination: pathlib.Path) -> dict

The TrustedPrincipal is a server-derived, authenticated and active identity
with scoped role, organization, project grants, permissions, session and user.
It must never be directly created from unchecked UI JSON. Prepare and send
are limited to the exact original actor and session. This restrictive pilot
does not provide a reauthorization/transfer mechanism for a new session.

Request IDs are stable 32-character lowercase hex strings. Proposal JSON
is canonical and bounded to 32 KiB. Only schema 1, source madar, ID,
taskId, projectId, title, createdUtc and optional expenseId/amountRial
are supported. amountRial is an optional bounded decimal metadata string,
NOT a posting instruction. No arbitrary finance, credentials or ledger data
are accepted. The stored fingerprint is SHA-256 of canonical payload JSON,
and is bound to the base revision, project, org, actor/session and immutable
prepare idempotency key.

Both prepare and manual send require separate explicit human actions.
Same-key replays are idempotent only with the same request, hash, revision,
organization and session. Manual send records an UNSENT authorization intent:
state MANUAL_SEND_AUTHORIZED, an immutable send key, unknown receipt state,
transportCalled=False, financialEventCreated=False. There is no network call.
Writes use BEGIN IMMEDIATE, FULL SQLite synchronization, and transactional
audit; exceptions rollback the request and its audit atomically.

Receipt observations are accepted only from an active, authenticated and
scoped taraz_adapter with mtr.receipt_ingest permission. Evidence must be
version 1, source taraz, at most 4 KiB, with exact keys observationId,
requestId, orgId, projectId, baseRevision, payloadSha256, sendKey,
result, receiptId and observedUtc. It must match the original request,
payload hash, send key and revision. Receipt result values are distinct:
unknown, not_received, received; only received has a receiptId.
The injected verified_by_adapter flag is a HOST ADAPTER ASSERTION,
not proof of independent receipt authenticity. The adapter must establish
Taraz provenance before calling this method. Stored observations are bounded,
checked for canonical encoding, hashes and state consistency on read.
Receipt_status reads only local metadata; it never modifies Taraz status.

Query-first recovery advice is one of:

- explicit_manual_send_required
- query_taraz_first_hold_unknown
- same_key_replay_only_after_authoritative_query
- recover_existing_receipt_only

UNKNOWN is not treated as NOT_RECEIVED. No automatic replay exists, even
after a verified not_received observation. A real peer adapter must query
first, preserve the same request/payload/key and respect prior manual
authorization. Receipt confirmation is not official financial posting.

## Backup and rollback plan

The backup_to method uses SQLite's consistent backup API to a temporary
SQLite file, checks quick_check and schema version, fsyncs the file and
publishes a create-only destination using an atomic hardlink. Existing
backups are never overwritten. Parent directory must be trusted and
protected by host filesystem ACLs. No uploads or external backups are made.

SQLite journal_mode=DELETE, synchronous=FULL and BEGIN IMMEDIATE protect
transactional consistency. On exceptions, modifications roll back.
To recover operationally, stop the host, retain a separate backup of its
current state, restore a verified backup to a NEW independent database path,
validate schema/integrity and counts, and only then plan an authorized cutover.
This module intentionally has no destructive in-place restore operation.
Publication directory fsync may be unavailable on Windows. Filesystem
durability still requires crash/power-loss acceptance on the target disk.

## Remaining mandatory integration dependencies

- Real LanService authentication/session lifecycle/ACL; never treat caller
  provided principal or current revision as authoritative without a trusted
  backend lookup.
- Atomic compare against the actual task/project revision at send boundary.
  The trusted current_server_revision parameter is only an injected
  assertion in this standalone component.
- Proven Taraz identity, authenticated query-first transport, compatible
  observation schema and server-side idempotency/replay guarantees. No
  official Taraz document or approval is created here.
- Host-managed access permissions, retention, secure backup/restore,
  interprocess lifecycle and disaster recovery, EXE and two-PC testing.
- Strong adversarial file protection. An OS attacker able to rewrite the
  SQLite database and recompute unkeyed hashes cannot be authenticated by
  this pilot; retain trusted OS ACLs, verified provenance and external audit.
  Link/reparse checks are not a replacement for secure parent directories
  against filesystem TOCTOU attacks.

## Synthetic checks

    python -B -m unittest discover -s tests -p test_mtr_host_request_store.py -v
    python -B -m unittest discover -s tests -p test_mtr_finance_workflow_contract.py -q
    python -B -m unittest discover -s tests -p test_mtr_deficiency_workflow.py -q

Set PYTHONDONTWRITEBYTECODE=1 for the local test process. All new tests
work only with TemporaryDirectory and synthetic principal/receipt snapshots.
They do not establish deployed or live finance acceptance.
