# MTR continuous execution contract — 2026-11-09

## Owner directive and finite-session boundary

The owner directs engineers to continue approved E0–E7 implementation without a new permission question or early status report for each incremental task. Continue safe independent phases even when a dependent phase is blocked. This does not authorize deployment, production financial writes, use of real user profiles, release, API spending, or bypassing human financial decisions.

This document persists task context, but DOES NOT start a background job. A chat agent cannot truthfully promise uninterrupted activity after its current execution ends. Each future authorized session should resume from the evidence ledger without asking the owner to repeat the design.

## Sources of truth

1. The approved Refine 6.2–6.29 decisions and original atomic note 1.28.
2. MADAR_TARAZ_RADAR_INTEGRATED_DESIGN_AND_ACCEPTANCE_20261109.md: acceptance AC-01..32, gates G-01..08.
3. MTR_EXECUTION_PHASE_PLAN_20261109.md and MTR_PHASE_EXECUTION_STATUS_20261109.md.
4. MTR_E7_ACCEPTANCE_GATES_20261109.md, actual isolated worktree source and observed test results.

Madar isolated worktree: D:/CoS-Test/000- Madar/madar-p2-gantt-notifications-20261107, original HEAD 32bd8ff. Taraz E2 detached worktree: D:/CoS-Test/000- Taraz/taraz-mtr-e2-isolated-20261109, original HEAD 653089b. Both have uncommitted work. The private LocalForge main remains the release reference until formally reconciled.

## Continuous engineering loop within each authorized execution

1. Take the next unaccepted AC/G gate, verify source/owner decisions and real file ownership.
2. Isolate work from other dirty files and from installed applications and finance.
3. Run baseline tests, create negative security/replay tests, implement smallest useful feature.
4. Run targeted tests and cross-repo smoke, then a stable full QA pass at integration checkpoints.
5. Record concrete file changes, command outputs, gaps and next dependency in the evidence ledger.
6. Continue directly to another independent safe work unit; do not stop just to narrate progress or request the same approval.
7. Never promote code-written or unit-tested status into deployed/accepted. No ledger mutation outside Taraz, no surprise cloud transfer or automatic send.

## Critical-path backlog

- E0: Complete schema, permissions, version and no-financial-side-effect contract.
- E2: Host-authoritative manual request/intent, authenticated Taraz peer, secure network transport and TLS pin, stable query-first retry, durable inbox/outbox, tenant ACL, verifiable receipts. Current device-local journal and file review are pilots only.
- E1 in parallel: Real manual order and CRM flows, optional AI local and online BYOK with verified per-user/project grants, privacy consent, secure secrets, spending control and manual review.
- E3: Join tested deficiency pure engine to real verified finance reviewer/assignee events, durable audit and manual-only re-submission with saved-state CAS.
- E4: Taraz official party read API scoped to organization; explain all visible matching candidates and differences, manual finance approval/audit, no automatic link.
- E5: Persist amendment-as-independent-request, explicit conflict and duplicate acknowledgements, version checks, rejection guidance and manual send, without altering original.
- E6: Deliver ACL-scoped internal notifications and read-only receipt/document-linked summaries only with authentic Taraz provenance.
- E7: All 32 AC and 8 G verified on installed dual-Windows LAN/TLS GUI, failure injection, backup/readback/rollback and separate approval before release.

## Tool and safety choices

- ECC for plan/test/review/security workflows; REA only for legally authorized source/behavior analysis; DevToys only as developer helper. None replaces the native product runtime by default.
- No destructive reset/clean of dirty worktrees. Do not overwrite another worker's files. No commit/push/install/publish until integration QA and release approval. Do not access real accounting profiles for synthetic tests.
- A source test can pass while deployed behavior is broken. The whole-source isolated QA during concurrent edits observed 221 Python modules executed, 190 passed and 31 failed. Do not call this green; triage by cause without restoring retired financial APIs solely for test appeasement.

## Valid blockers

If a step needs untrusted finance identity, a real billing credential, cross-tenant data, unclear third-party license rights, release permission or destructive production action, stop ONLY that step, document why, and continue another independent authorized phase. Never guess completion or results. Send one consolidated checkpoint at the end of actual execution, not a sequence of status-only replies.
