# E3 durable deficiency metadata pilot — 2026-11-09

**Status:** Isolated SQLite-backed prototype. This is NOT operational E3 acceptance or a financial integration.

## Implemented boundary

Added only three new files in the Madar isolated worktree:

- mtr_deficiency_store.py: explicit-path bounded SQLite state/audit store
- tests/test_mtr_deficiency_store.py: disposable Windows SQLite tests
- this pilot evidence document

Existing source and tests were not edited. The existing pure-domain module mtr_deficiency_workflow.py is called for each transition and remains the validation authority. Approved Refine 6.6–6.8 / AC-08..10 requires that finance may assign a deficiency to a specifically authorized user, the assignee records a result, and return to finance requires a **separate explicit authorized manual action**. This pilot preserves all those distinctions without attempting to send or post anything.

## Durable APIs and invariants

| API | Local behavior |
|---|---|
| DeficiencyStore(absolute_sqlite3_path) | Creates the isolated database at an explicitly supplied path with existing parent; rejects foreign/unversioned/malformed schemas and symlinks/junctions |
| refer(case, receipt, reviewer, assignee, deadline, reason, missing_fields, event_id, occurred_at) | Uses the pure finance referral validator; persists a unique, scoped receipt metadata, actor, assignee, deadline, reason, missing fields and first audit event |
| resolve(baseline, actor, saved_baseline, corrections, result_note, event_id, occurred_at, expected_version) | Assigned, authenticated user only; newer server-saved baseline and optimistic version check; records resolution as CORRECTED_READY_FOR_RESUBMIT without sending |
| prepare_manual_intent(baseline, actor, current_server_baseline, server_revalidated, explicit_manual_action, warning_acknowledged, new_send_key, event_id, occurred_at, expected_version) | Separate authorized, explicitly manual step and fresh baseline confirmation; records MANUAL_RESUBMISSION_INTENT_ONLY, never transport or ledger posting |
| read_case(baseline, principal) | Restricts org/project and case visibility using an active, authenticated server-injected Principal |
| query_first_status(baseline, principal) | Returns UNKNOWN_REQUIRES_AUTHENTICATED_TARAZ_QUERY, peerAuthenticated=False, receiptVerified=False, newSendPermitted=False, postingPerformed=False; this is **not** a peer query |

Primary key: organization / project / request / original revision. Org-scoped unique finance receipt metadata IDs, event IDs and manual intent send keys; immutable SQL audit triggers; optimistic compare-and-swap version; content-hashed deterministic bounded JSON snapshots cross-checked with ordered audit table at readback. Identical event replay is accepted without a second write; different payload under the same event ID is rejected. SQL BEGIN IMMEDIATE and rollback ensure that case state and event audit commit together on the local database.

Bounded resources: 2,048 maximum cases per DB, 16 events per case, 32 KiB case snapshot, 8 KiB event, 4 KiB SQLite page size and 32,768 pages (approximately 128 MiB cap for the main DB; temporary journal files can consume additional space). Full synchronous SQLite journal writes and foreign-key enforcement are enabled.

No official Taraz ledger, invoice, party, document, network, service, customer profile or real data is accessed. Every returned view has financialEventCreated=False, postingPerformed=False, financeApprovalVerified=False, peerVerified=False, officialDocumentId=None. The stored receipt identifier denotes only supplied **adapter-asserted local metadata**, never a verified official finance document.

## Observed tests

From the isolated Madar worktree, ran:

    python -B -m unittest -q tests.test_mtr_deficiency_store tests.test_mtr_deficiency_workflow

**65 tests OK, exit code 0** in 2.614 seconds: **28 new durable-store tests** and **37 existing pure-workflow tests**.

Coverage includes restart/readback, ACL (actor, organization, project, role and assignee), wrong/stale/mismatched or unverified receipt claims and invalid deadlines, duplicate referral, idempotent matching events, conflicting event/send keys, incomplete-business-data warning, missing manual action, stale revision compare-and-swap, two-thread duplicate/conflict races on Windows SQLite, corrupted snapshot/audit rejection, immutable audit SQL triggers, abort-after-case-update transaction rollback, foreign database nonadoption, and symlink or wrong-version rejection. No source or finance side effects occurred.

The **first exploratory test run** encountered Windows TemporaryDirectory cleanup errors because test-owned direct SQLite connections were not closed explicitly. The new test module was corrected to close every direct connection; the **later 65-test run** is the successful observed result. No existing-file change was needed.

## Blocking limits, not inferred proof

1. Trusted Principal, FinanceReceipt.verified_by_adapter and server_revalidated are **assertions injected by a trusted host adapter**. This module cannot authenticate Taraz, prove a finance reviewer identity, or verify an official receipt. Caller-created claims are not security evidence.
2. The read-only query-first status is always UNKNOWN and never initiates network contact. There is no peer transport, actual ledger-side idempotency, authoritative status reconciliation, signed formal receipt, official document ID or accounting posting.
3. SQLite CAS is atomic only over this metadata file. It does NOT atomically compare the current official Taraz revision with a LAN send or guarantee exactly-once finance effects.
4. Local database corruption tests do not prove protection against administrators who can rewrite tables and hashes, malicious database-directory writers, hostile OS path races, loss of machine power, or backup/restore failure. Those require isolated operational tests.
5. Real MadarHost authentication, ACL enforcement and two-device LAN/WebView2 tests, finance deficiency routing, certified Taraz adapter, released EXE and AC-08..AC-10/G-01..08 full acceptance are still open. No commit, push, install or deploy occurred.
