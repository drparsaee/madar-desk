# MTR E5 host-authorized amendment adapter pilot — 2026-11-09

**Pilot only. No real LAN route, official Taraz receipt, posted financial document or automatic finance send.**

## Change scope and trust boundary

New files only in the isolated Madar worktree:

- mtr_amendment_host_adapter.py: host-only, strict JSON interpreter around the existing mtr_amendment_store.AmendmentStore.
- tests/test_mtr_amendment_host_adapter.py: disposable Windows SQLite and synthetic LanService/bridge tests.
- This evidence document.

No edit to lan.py, native_app.py, mtr_amendment_store.py, existing tests, E7 audit, real LAN users/profiles, application installer, or Taraz. No commit, push or deploy.

The adapter requires a host-supplied service exposing account_for(token), service.lock and bridge._lock. It calls account_for(token) **afresh inside both locks, in the existing LAN order (service.lock then bridge._lock)**. It derives user_id, LAN session identity, role, project membership and explicit financeEdit from the current authenticated host account, never from command_json. The host injects org_id and a separate operator-maintained finance_reviewer_usernames frozenset at adapter construction.

Existing LAN account roles are admin/editor/viewer; there is **no native finance_reviewer role**. Therefore a finance reviewer for this isolated pilot means an admin/editor with financeEdit=True AND explicit host-operator allowlist membership. Without both, review and manual-unsent-intent deny by default. Editors also require an exact nonempty projects grant. Admins must have projects=None; unknown/ambiguous scope denies. Creation and query for nonreviewer editors are allowed only when financeEdit=True and project scope is valid. Underlying store additionally binds draft ownership to original actor and session, so another reviewer cannot silently assume an editor's draft.

These permissions are **host adapter assertions** and do not establish that a person is an independently authorized Taraz finance reviewer. The adapter does not authenticate credentials itself, expose an HTTP endpoint, mount a service, control TLS, or authorize a cross-organization financial operation. Integration must use the real, properly configured and TLS-protected LanService account/session API, followed by independently authenticated Taraz identity and finance grants.

## Versioned saved-card and command contract

Requires one uniquely matching saved project and one uniquely matching saved task in the current bridge.getState result. The synthetic card may contain an explicit metadata object named mtrFinanceOriginal with EXACTLY requestId, submitted=True and a bounded scalar fields mapping. Absence, foreign project, duplicate IDs, invalid fields or non-true submitted marker fails closed. The adapter hashes **the full saved project and task JSON** to get a current 64-hex digest under both locks, and derives an amendment original with request ID, host org, saved project, original scalar fields, and a task-based revision derived from that hash.

The boolean submitted marker is **not an authenticated receipt or proven financial submission**. It could be edited in the host card by an existing user able to write the card. Consequently this is a synthetic contract, NOT reliable production provenance. Real integration must bind original request ID, immutable snapshot and revision to an authenticated, scoped Taraz receipt or host-authoritative finance request registry before allowing a production finance workflow.

Client command_json is a UTF-8 Python string bounded to 8,192 encoded bytes. Duplicate keys at any nesting level are rejected, including duplicate proposed field names. Non-finite JSON values, invalid JSON, unknown keys, extra actor/org/receipt/verification controls, wrong types, unrecognized actions, invalid IDs or illegal field data fail closed. Every command must supply projectId, taskId and expectedTaskDigest. Only these four exact action schemas exist:

| Action | Additional command fields | Behavior |
|---|---|---|
| create | amendmentId, proposedFields, createKey, acknowledgedOpen, acknowledgedDuplicate, acknowledgedAt, previousRejectedAmendmentId | Delegates to existing AmendmentStore.create_amendment; existing related/open/duplicate warnings remain independent |
| review | amendmentId, reviewMode (choose_fields or re_review_baseline), expectedRowRevision, chosenValues, operationKey, occurredAt, acknowledgedDependencyFields, acknowledgedRevisionChange | Only host-allowlisted finance reviewer may review; validates current saved original and revision, then delegates pure comparison and persistent review/CAS to AmendmentStore |
| manual_unsent_intent | amendmentId, expectedRowRevision, sendKey, explicitManualAction, occurredAt | Requires fresh saved task and separate explicit true manual action; delegates to AmendmentStore.manual_send_intent with host-verified current saved snapshot; **NEVER sends** |
| query | amendmentId | Read-only local store lookup; checks current LAN token/scope, saved project/task and exact original request binding |

No caller-controlled principal, orgId, currentOriginal, currentServerVerified, sourceVerified, finance actor role, Taraz receipt/rejection or ledger action is accepted. No action for reject/approve/post/send exists. The existing store's record_rejection operation is intentionally **not reachable** because authentic Taraz rejection/source validation is not yet independently available. Stale card hashes are refused before store calls; changed saved originals require explicit review re-evaluation and the store's row CAS. A token change also changes the stored session pseudonym, so it does not silently inherit an older session's ownership.

Every result includes hostAuthenticated=True (the **adapter saw a successful host account_for call**, not proof that a real LAN test was run), hostFinanceReviewerAssigned, tarazReceiptVerified=False and transportState=NOT_SENT_BY_ADAPTER. Existing store results preserve sentToTaraz=False and officialFinancePosted=False. No full bearer token or account password hash is returned or persisted by this new adapter. The stored session identifier is a fixed-length SHA-256-derived pseudonym, not the bearer token.

**Clock boundary:** acknowledgedAt and occurredAt in this isolated contract are caller-provided display/audit timestamps checked by the existing store for timezone syntax. This adapter does NOT provide an independently trusted host clock or cryptographic event timestamp. Those values must not be used as official finance audit proof; production integration requires host-issued and durably replay-bound event times.

## Actual synthetic tests

From the isolated Madar worktree, ran:

    python -B -m unittest -q tests.test_mtr_amendment_host_adapter tests.test_mtr_amendment_store tests.test_mtr_amendment_review_preview

**86 tests passed, exit code 0, 2.861 seconds** in the latest verification run: 28 tests in the new host adapter suite and 58 existing amendment store/preview tests.

Coverage included synthetic authenticated/revoked LAN sessions, financeEdit and role denial, explicit host reviewer allowlist, cross-project and absent project membership, duplicate JSON keys and unauthorized principal/org/receipt controls, malformed fields and missing submitted marker, stale task and project hashes, changed original request ID, frozen/restarted local draft, query-only read, manual true-only unsent intent, changing original re-review acknowledgement, idempotent create/replay, mutually exclusive competing send intents, simultaneous saved-card edit under host locks, no token/password disclosure, no LAN/ledger transport, and no host saved-state mutations.

All test profiles and SQLite databases were synthetic under TemporaryDirectory. The LAN service was a synthetic stand-in implementing account_for/locking semantics, **not a live LanService socket, Windows service, TLS connection, or authenticated real-user integration**. Existing store tests cover durable restart and cross-process behavior separately; this new adapter suite did not conduct real LAN communication.

## E5 release/acceptance blockers

1. Current saved mtrFinanceOriginal metadata is synthetic and not a proven Taraz submission/receipt. Host ACL and task revision do not bind it to an authentic official financial record. AC-20..AC-30 remain open.
2. Reviewer authorization is an independent host-operator allowlist plus financeEdit; there is no native LAN finance-reviewer role or verified Taraz finance-review identity in this pilot. Creator/session ownership limitations remain unchanged in AmendmentStore.
3. The adapter stores only local drafts, decisions and manual-unsent intents. It cannot post invoices, use Taraz finance APIs, verify rejection status, transport a request, return a signed official document ID, or guarantee ledger idempotency. There is no route registration.
4. The server lock and task digest protect a single host's local snapshot transaction only, not concurrent changes to an independent Taraz database or two-PC remote connection. Installed app compatibility, time provenance, full security/backup/restore, real LAN TLS/reconnect and actual finance audit remain unverified.

**Disposition:** scoped E5 host adapter pilot, not E5 production acceptance, no E0–E7 completion claim. No commit, push or deploy was performed.
