# MTR E5 | Durable, independent amendment pilot (2026-11-09)

**Status: unit-tested local prototype only.** Not a released Madar workflow,
connected Taraz API, official accounting mechanism, or finance migration.
Tests use synthetic SQLite data only.

Source: mtr_amendment_store.py, dependent on existing pure module
mtr_amendment_review_preview.py. Standard-library SQLite for persistence.

## Host-facing API

Instantiate AmendmentStore(path: pathlib.Path) using a host-chosen absolute
.sqlite3 path beneath a trusted, OS-ACL-protected directory. Pass a server-
derived TrustedPrincipal containing user_id, session_id, org_id, role,
project_ids, permissions, authenticated, session_valid and active. Never
construct such a principal from unchecked UI input.

All mutation methods take keyword-only arguments:

    create_amendment(principal, original, amendment_id, proposed_fields,
                     create_key, acknowledged_open, acknowledged_duplicate,
                     acknowledged_at=None, previous_rejected_amendment_id=None)
    choose_fields(principal, amendment_id, expected_row_revision,
                  chosen_values, operation_key, occurred_at)
    re_review_baseline(principal, amendment_id, expected_row_revision,
                       current_original, chosen_values,
                       acknowledged_dependency_fields,
                       acknowledged_revision_change, operation_key, occurred_at)
    manual_send_intent(principal, amendment_id, expected_row_revision,
                       current_original, send_key, explicit_manual_action,
                       current_server_verified, occurred_at)
    record_rejection(adapter, amendment_id, expected_row_revision,
                     observation_id, receipt, verified_by_adapter, occurred_at)

Read-only methods:

    get_amendment(principal, amendment_id)
    audit_events(principal, amendment_id)
    related_amendments(principal, org_id, project_id, original_id)

Separate backup-writing method (creates a NEW destination file):

    backup_to(destination: pathlib.Path)

Each amendment has its own globally unique ID, immutable link to original,
immutable original and creation snapshots, org/project/actor/session scope,
independent row revision, conflict decisions, audit and stable keys. SQLite
triggers prevent direct update of the original identity/snapshot and audit
update/delete; JSON is bounded, canonical and hashed, with verification on
reads. Stored statuses are DRAFT, MANUAL_SEND_INTENT, REJECTED. In this
module **MANUAL_SEND_INTENT is not transmitted**; every result reports
sentToTaraz=False and officialFinancePosted=False. No ledger, posting,
party, payment, invoice, email, background send or Taraz network request.

### Approved decisions and gates

- Creating a new independent amendment derives the related list from the
  same SQLite transaction. The existing pure preview_create_amendment API
  detects open-amendment and possible-duplicate warnings separately and
  requires two distinct human acknowledgments if both apply. Each warning
  acknowledgment receives a separate audit event. New amendments can link
  to an existing REJECTED amendment without changing the rejected original.
- Pure review_field_choices handles explicit per-field conflict decisions.
  Pure review_changed_baseline reopens only affected fields and requires
  appropriate revision/dependency confirmations. Every write checks row CAS,
  operation-key uniqueness and principal session/ACL in BEGIN IMMEDIATE.
- Pure preview_manual_submission runs before each manual send-intent
  authorization, including idempotent replays, with current original and
  related snapshot checks. Unresolved conflicts and stale original/related
  versions block the intent. A distinct manual action and fresh host snapshot
  assertion are required. No send is performed.
- record_rejection accepts only a scoped, authenticated taraz_adapter
  asserting verified Taraz provenance. The pure rejection guidance function
  proposes fields only when a verified, structured reason explicitly
  identifies them. An ambiguous/free-text reason produces no invented
  correction. Rejection observations remain independent of the original
  request, and are neither automatically sent nor posted.

## Durable operations, backup and rollback

SQLite uses BEGIN IMMEDIATE, journal_mode=DELETE, synchronous=FULL, foreign
keys, unique keys and transactionally appended audit. A mutation error rolls
back the data update and corresponding audit event. The bounded audit is
immutable by SQLite update/delete triggers. This is not an external tamper-
proof audit against a privileged attacker controlling the full database.

backup_to(destination) makes a consistent SQLite backup using the SQLite
backup API, checks integrity and schema, fsyncs the file and publishes it
create-only. It never overwrites an existing backup or performs restore.
An operational rollback requires stopping the host, preserving current
state, independently restoring a checked copy to a NEW path, verifying
integrity/counts and separately approving a cutover. Windows directory-
entry fsync and physical power-loss guarantees have NOT been verified.

## Dependencies still open

1. Real LanService must derive all identity/session/role/grants and actual
   original request revisions from its server authority, never client flags.
   The caller-injected current_server_verified and verified_by_adapter values
   are assertions here, not independently authenticated evidence.
2. Actual send boundary must atomically check current project/original and
   related revisions and enforce Taraz-side query-first/idempotency. This
   pilot has no transport or official finance authority.
3. Exact Taraz receipt schemas and authenticity, signed authoritative
   rejection evidence, durable handoff, official-document referents, failure
   recovery, secure backup retention, abandoned-session reauthorization,
   GUI/EXE acceptance and two-machine integration remain unverified.
4. A SHA-256 digest detects accidental inconsistency, not a privileged
   attacker capable of rewriting metadata plus digests. Trusted filesystem
   access is required. Preflight link checks cannot eliminate all TOCTOU
   opportunities in attacker-writable parent directories.

## Reproducible synthetic tests

    $env:PYTHONDONTWRITEBYTECODE='1'
    python -B -m unittest discover -s tests -p test_mtr_amendment_store.py -v
    python -B -m unittest discover -s tests -p test_mtr_amendment_review_preview.py -q
    python -B -m unittest discover -s tests -p test_mtr_finance_workflow_contract.py -q

These tests use disposable TemporaryDirectory SQLite files and synthetic
principals. They do not prove production finance correctness or deployment.
