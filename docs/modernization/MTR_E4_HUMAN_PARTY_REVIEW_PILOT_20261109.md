# MTR E4 durable human party-review pilot — 2026-11-09

**Status: isolated, metadata-only pilot. NOT official Taraz party linking, authoritative party creation, production authentication, or E4 acceptance.** All tests used disposable Windows temporary SQLite databases, synthetic identities and simulated candidate records. The pre-existing E7 acceptance matrix and E4 preview were not edited.

## New files and design basis

- radar_party_review_store.py: stdlib SQLite pending review and a single explicit human decision.
- tests/test_radar_party_review_store.py: synthetic authorization, integrity, replay, restart and concurrency tests.
- This document: test evidence and deployment blockers.

Follows approved Refine 6.11–6.14 / AC-14–AC-17. The existing pure radar_party_match_preview.preview_party_matches function is the only candidate comparison logic. This new store does not rank, score, filter, merge, guess official IDs, create official parties, update party details, attach a link to an order or call Taraz. Refine 6.15–6.16 correction-impact/selective updates and AC-18–AC-19 are outside the isolated pilot.

## Trusted host and source boundary

HostPrincipal contains user_id, organization_id, session_id, role, project_grants, capabilities, visible_fields, allowed_candidate_ids, authenticated and active. The store requires an active authenticated taraz_finance_reviewer and an explicit project grant. Opening requires party_match_read and party_match_decide; read/list requires party_match_read, and a decision requires party_match_decide. Every open, read and decision rechecks the stored candidate list and visible fields against the current host-provided grants. After a field or candidate grant is withdrawn, detailed read/decision fails closed and the pending list omits that case. **These are assertions supplied by the host adapter**, not independently authenticated here; production clients must never be permitted to fabricate this Principal.

The caller must supply the complete preauthorized candidate records, an explicit ordered authorized_candidate_ids tuple, temporary customer, permitted visible_fields, source_ref, positive source_revision, expected_source_digest and explicit source_binding_host_confirmed boolean. The store recomputes the explainable preview from all supplied candidates and compares their ordered IDs exactly. Missing, duplicated, foreign-organization or unauthorized rows reject the entire batch without a partial result. All authorized candidates remain in original order including no-match and conflicting claimed-verified official IDs. Each candidate retains all four field comparison results with unauthorized field values masked. The store saves **only this redacted preview**, never unredacted candidate input.

The digest is SHA-256 over deterministic UTF-8 JSON of the redacted preview. At opening it must equal the caller-supplied expected source digest; at decision time it must agree with the current source digest and revision, both explicitly supplied by a trusted host. A decision is refused if the stored source binding or current host binding assertion is false. **Neither a digest nor a boolean proves genuine Taraz provenance.** The external host must establish authoritative, authenticated, same-tenant source identity, field grants and revision. Every review view explicitly reports sourceAuthenticityVerifiedByThisModule=False.

## Durable SQLite schema and APIs

Primary key: organization/project/review ID. Org-scoped unique event ID, bounded snapshot and its SHA, allowed candidate IDs, field grants, source reference/revision/digest, optimistic version and immutable audit entries. Local states:

| State | Human-only transition |
|---|---|
| PENDING_HUMAN_REVIEW, version 1 | open_pending records complete scoped preview and opening audit; creates no party decision |
| DECISION_RECORDED, version 2 | record_decision accepts select_candidate for a listed candidate ID, or reject_all without a candidate ID; both are local human decisions |

record_decision requires expected_version=1, expected_snapshot_sha256, current_source_ref, current_source_digest, current_source_revision, source binding confirmation, explicit event ID and UTC timestamp. Selecting a candidate with a conflict explanation additionally requires acknowledge_conflicts=True. Optional human note is never compulsory. Actor ID, session, timestamp, decision and original snapshot/source/revision are audited. No automatic linking, merging or second finance approval is performed.

read_review returns scoped pending/decided state and original explanations. list_pending returns a bounded (1–64) **query-only** index scoped to org/project; other organizations see no foreign rows. Every response contains officialTarazPartyCreated=False, officialPartyLinked=False, officialPartyUpdated=False, automaticMergePerformed=False and networkUsed=False.

Explicit absolute .sqlite3 path with pre-existing parent, SQLite BEGIN IMMEDIATE, synchronous FULL, foreign-key enforcement and strict application ID/schema checks. Bounded to 2,048 reviews, 64 candidates/review, 48 KiB snapshot, 4 KiB audit event and 128 MiB main SQLite database pages. Transient journals can require additional disk space. Canonical bounded JSON, snapshot hash, candidate list, field masks, audit rows, decision actor/session and revision are checked at readback. Exact event replay is recognized without rewriting audit; changed event ID/payload is rejected. SQL triggers prevent audit UPDATE/DELETE; review decision and its audit event commit or roll back as one local transaction.

## Observed test results

Command from the isolated Madar worktree:

    python -B -m unittest -q tests.test_radar_party_review_store tests.test_radar_party_match_preview

**40 tests, OK, exit code 0, 3.026 seconds** in the latest observed verification run. **29 new durable-store tests plus 11 existing pure-preview tests**.

Tests cover Windows SQLite restart, full authorized candidate and conflicting-ID explanation retention, no auto-merge or official party claim, optional human note, explicit selection/rejection, source-binding and stale source reference/digest/revision rejection, cross-organization/project permission boundaries, **current field/candidate grant revocation**, field-level private-data redaction inside the SQLite snapshot, role/session/actor audit, exact replay, conflicting event IDs, concurrent duplicate opens and competing decisions, corrupted metadata detection, immutable audit SQL triggers, audit insertion failure rollback, foreign database refusal, symlink/invalid-path and size bounds.

The first exploratory run found a new-file implementation mistake: checking type(path) is Path rejected normal WindowsPath subclasses. This was fixed to isinstance(path, Path). Later exploratory tests exposed two test assumptions: a foreign organization pending-query safely returned an empty list instead of raising, and a test helper accidentally cleared an explicit candidate under reject_all. Both were corrected only in owned new files. The final 40-test run supersedes these exploratory failures.

## Explicit blockers

1. The trusted Principal and host source binding are not actual authentication. The host must verify the user's session, revocation, role, organization, project and authenticated Taraz party catalog provenance. A forged caller-supplied boolean or digest is insufficient.
2. A recorded selected candidate is **not an official Taraz party link**. No Taraz party API, database mutation, document update, finance approval or ledger posting occurs.
3. The SQLite compare-and-swap is local only. There is no atomic catalog-revision reconciliation with Taraz, TLS/LAN transport or real multi-device acceptance.
4. Tests do not prove resilience to hostile local database administrators who can rewrite hashes, a physically interrupted machine, cross-service backup/restore, real Windows installations, official Taraz data, or AC/G end-to-end acceptance.

No existing source/tests/docs, live profiles, network/services, Taraz official records, commits, pushes, installs or deployments were changed.
