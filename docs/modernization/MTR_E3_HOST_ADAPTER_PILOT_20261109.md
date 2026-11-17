# E3 Host-only deficiency adapter pilot | 2026-11-09

Status: isolated, synthetic-tested, metadata-only implementation. NOT a
production Madar/Taraz finance connector, officially verified receipt
processor, installed LAN route, transport, accounting system, or deployment.
No official ledger, invoice, finance approval or automatic send occurs.

Source: mtr_deficiency_host_adapter.py
Tests: tests/test_mtr_deficiency_host_adapter.py
Existing dependencies, unchanged: mtr_deficiency_store.py,
mtr_deficiency_workflow.py and LanService.account_for.

## Host-facing Python-only API

Construct:

    DeficiencyHostAdapter(
        service, store: DeficiencyStore, *,
        org_id: str,
        reviewer_usernames: frozenset[str] = frozenset(),
        verified_receipt_source = None)

Methods (all keyword-only arguments):

    read_case(token, project_id, task_id, case_revision, case_digest,
              expected_host_revision, expected_host_digest)
    query_first_status(token, project_id, task_id, case_revision,
                       case_digest, expected_host_revision, expected_host_digest)
    refer_from_trusted_receipt(
        token, project_id, task_id, expected_host_revision,
        expected_host_digest, assignee_username, deadline, reason,
        missing_fields, event_id, occurred_at)
    resolve_saved_fields(
        token, project_id, task_id, case_revision, case_digest,
        expected_case_version, expected_host_revision,
        expected_host_digest, corrected_field_names, result_note,
        event_id, occurred_at)
    manual_resend_intent(
        token, project_id, task_id, case_revision, case_digest,
        expected_case_version, expected_host_revision,
        expected_host_digest, explicit_manual_action,
        warning_acknowledged, new_send_key, event_id, occurred_at)

Nothing is registered on a LAN or HTTP route. The adapter acquires
service.lock then service.bridge._lock before calling account_for(token),
checking the currently registered account/project/role grants, and reading
bridge.getState(). Client/offline bridges and stale/ambiguous task/project
snapshots fail closed. Organization ID is host-configured, not client chosen.

Existing LAN roles are admin/editor/viewer, not a real Taraz finance reviewer
identity. Finance review permission therefore requires an explicit
operator-owned reviewer_usernames allowlist, plus current admin/financeEdit
editor permission and project scope. An ordinary current project editor may
be assigned to resolve missing fields, but does not gain authority to refer
or manually resend. Revoking a reviewer's finance grant removes review/read
authority unless that person remains the assigned resolver independently.

## Provisional host-saved case binding

The pilot expects a previously host-saved task marker named
mtrDeficiencyRequest, with exactly these fields:

    {
      "requestId": "original-request-id",
      "revision": 3,
      "reviewState": "IN_FINANCE_REVIEW",
      "expectedReceiptId": "official-source-receipt-id",
      "receiptGeneration": 7,
      "previousReceiptIds": [],
      "previousSendKeys": []
    }

The stable request ID and positive, increasing revision originate from the
host-saved card. The adapter computes a SHA-256 over canonical saved
project/task JSON (maximum 64 KiB), rather than trusting a browser-provided
digest. Caller-provided expected revision/digest are checked against that
current host snapshot inside both locks. Edits require a new saved
revision and changed digest for resolution. This marker is a PROVISIONAL
host-side schema and is not independently authenticated receipt evidence.
Real host code must implement trusted creation and monotonic revision/CAS
before operational use.

An assignee first saves corrected values to the existing task through normal
host persistence, in a bounded mtrDeficiencyFields dictionary. For
resolve_saved_fields, the caller submits only a frozenset of field names.
The adapter reads exact already-saved string values from the current host
task under the lock. The existing DeficiencyStore and pure workflow enforce
that these fields belong to the assigned deficiency, a new changed baseline
is used and the correct assignee acts. A result is only a correction record,
not a new official financial event.

## Independent receipt provenance boundary

The constructor defaults verified_receipt_source to None. Without an
independently authenticated Taraz receipt adapter, ALL referral-creation
calls are denied BEFORE any deficiency-store write. Existing scoped case
reads and local query-first status remain available.

Synthetic trusted host Python tests may inject an object with:

    verified_receipt_for(*, baseline: Baseline) -> FinanceReceipt

The injected source must independently authenticate its Taraz-direction
receipt before returning it. The host adapter checks exact type, request,
organization/project, saved revision and digest, expected receipt ID and
generation, source and verified flag; the pure domain then checks current
review status and timestamp. This is only an INJECTED ASSERTION; the pilot
cannot independently prove Taraz provenance. The test source is synthetic.

No public method accepts a browser-provided receipt, verified_by_adapter
boolean, principal, role, org ID or server_revalidated flag. Returned local
metadata intentionally reports no official finance verification or posting.
The pilot must not be mounted as a route until a real verified source exists.

## Durable transitions and query-first semantics

- Referral: an authorized finance reviewer refers a matching, independently
  verified deficiency to a current authorized assignee with reason, deadline
  and audit. Existing DeficiencyStore handles transaction, duplicate receipt,
  event idempotency and corruption checks.
- Resolution: only the currently scoped assigned user may attest missing
  fields already saved in the host task. A newer current baseline and case
  version are required. The state becomes CORRECTED_READY_FOR_RESUBMIT.
- Manual resend: separate explicit human action, finance reviewer grant,
  fresh host baseline, unique send key, current case version and incomplete
  data warning acknowledgment. This produces only a durable
  MANUAL_RESUBMISSION_INTENT_ONLY, NEVER an actual Taraz send or posting.
- Read/query-first: only scoped, active host users related to the case can
  view details; a revoked reviewer cannot continue reading by username alone.
  query_first_status always reports an UNKNOWN peer state requiring a real
  authenticated Taraz query. Unknown is not proof of non-receipt.

The existing DeficiencyStore stores its own independent SQLite metadata
with BEGIN IMMEDIATE, audit and integrity rules. No original task mutation
or official financial document is performed here.

## Open operational dependencies

1. No verified official Taraz receipt source is implemented. Default referral
   DENY must remain until externally authenticated receipt provenance exists.
2. The saved task marker and monotonic numeric revision must become a
   trusted host-generated/CAS-controlled contract. Current task fields may
   otherwise be user-editable. Digest checks alone cannot prove origin.
3. Future live transport must independently query Taraz, preserve stable
   request/send keys, and enforce authoritative idempotency and formal finance
   state separation.
4. Host-supplied review event timestamps must be replaced by server-generated
   trusted time if a new web endpoint is ever designed. No endpoint exists now.
5. Production LanService integration, actual user/profile migrations,
   financial documents, client/host concurrency, two-PC/EXE, physical
   power-loss, backup restoration and receipt cryptographic verification
   remain untested.

## Synthetic test commands

    $env:PYTHONDONTWRITEBYTECODE='1'
    python -B -m unittest discover -s tests -p test_mtr_deficiency_host_adapter.py -v
    python -B -m unittest discover -s tests -p test_mtr_deficiency_store.py -q
    python -B -m unittest discover -s tests -p test_mtr_amendment_host_adapter.py -q

All new tests use a synthetic locked LanService, temporary SQLite stores,
fake sessions and a Python-only synthetic receipt source. They are not
operational or financial acceptance tests.
