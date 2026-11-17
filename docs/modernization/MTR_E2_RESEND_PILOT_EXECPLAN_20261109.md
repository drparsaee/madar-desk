# E2: replay-safe manual metadata proposal, isolated Madar pilot

## Purpose and exclusions

Owner 2026-11-09: implement approved phases with priority on the Madar/Taraz connection. Worktree `D:\CoS-Test\000- Madar\madar-p2-gantt-notifications-20261107` at baseline `32bd8ffe5ebbb0f4cd5c011c59323ed32f8647ac`. Scope this slice to the existing schema-1 *non-financial metadata* proposal. Do not alter user profiles, live app, installed host, ledger, Parsian, network settings, or Taraz main branch. No commit, push, release or posting.

## Existing behavior / overview

- `taraz_exchange.queue_saved_task(state, task_id, expense_id=None)` validates one saved card and writes `pending/<random-id>.json` using a temporary file.
- Each call generates a fresh UUID, even if caller retries the same authorized send after losing its response.
- Taraz independently reviews/rejects metadata and moves it to `reviewed`; no financial event is created.
- `native_app.Bridge.tarazIntegrationQueue` exposes only the existing manual workflow. The UI receives the generated ID. No durable resend token is saved by the UI.
- Baseline `py -3.12 -B -m unittest -q tests.test_taraz_exchange tests.test_taraz_review_status` => **11 tests OK**.

## Design and parity

Add an *optional explicit* `request_id` (32 lowercase hexadecimal characters) for retries of an **already authorized** proposal. No `request_id` preserves the existing manual-new-send semantics. A retry with the same request ID must:

1. Compare validated original task/project/title/selected expense/amount against the same previously stored payload (ignore only original `createdUtc`).
2. Return existing ID with `replayed=True` and **never** write/overwrite a new file when exact match is found in pending/reviewed.
3. Fail closed on conflicting payload, unsafe root/file, simultaneous pending+reviewed or interrupted file; do not regenerate a fresh ID silently.
4. Create the proposal only once with exclusive destination publication. No receipt means no assertion of financial acceptance.

This is a scoped backend building block, not full E2: no authenticated peer, true LAN transport, persisting retry intention before dispatch, independent amendment, money posting, or external receipt.

## Tests, edge cases and rollback

Temp `LOCALAPPDATA` only; exact retry, mismatch, reviewed retry, conflict, invalid ID, path safety, no finance posting, existing baseline and synthetic cross-process coverage. Any failed/unknown query must not trigger automatic sending.

Rollback by reverting **only** this pilot's scoped source and tests in isolated worktree. No actual profiles/financial records accessed. Release requires E2 authentication/inbox contract and physical LAN/desktop acceptance separately.

## Progress

- [x] Read existing source and targeted tests; baseline 11/11.
- [x] Implement optional explicit replay key without default behavior changes: `taraz_exchange.queue_saved_task(..., request_id=...)`, native optional `requestId`, task history pending-item retry button with explicit confirmation. The ID is **not yet durably recorded by UI before its first send**; this is a significant remaining E2 recovery gap.
- [x] `py -3.12 -B -m unittest -q tests.test_taraz_manual_retry tests.test_taraz_exchange tests.test_taraz_review_status tests.test_ai_user_admin`: **25 tests OK**, exit 0. Includes exact replay, conflicts, reviewed retry, invalid ID, and exclusive publication collision. Baseline original two modules 11/11 passed.
- [x] `node --test tests/general_ui_preferences.test.cjs`: **4 tests passed**; `node_modules/.bin/vite.cmd build`: **successful**, warning for 500+ kB main chunk. `git diff --check`: exit 0 on tracked files. This is *not* browser E2E of retry and not installed Windows acceptance.

## Further E2 limitations / decisions

- A user clicking new send still creates a new ID. On lost first response the UI can fetch a pending local proposal (when readable) and explicitly select retry of the same ID, but without an authenticated Taraz query it is not allowed to infer reliable delivery. A validated prior proposal missing from disk is not proof of nondelivery.
- Publication uses an exclusive hard link from a completed, flushed temporary file on the local Windows filesystem. Unsupported filesystem / hard-link failure fails closed; directory durability after sudden power loss and true cross-machine transport remain unproven.
- A retry of a reviewed proposal only confirms the exact same **local** metadata exists; it is not a formal accounting receipt, and no posting takes place.
- Do not activate automated retry or claim idempotency of ledger side effects. The independently isolated Taraz recovery pilot requires a separate cross-repo test after its source is ready.
