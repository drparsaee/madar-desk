# E2 local first-send journal pilot — 2026-11-09

## Goal and scope

Refine 6.5/6.10 require explicit manual first send and safe same-key replay when the previous response is unknown. Prior source created the request UUID only inside file publication, leaving a crash window before the UI learned it. This isolated pilot reserves an ID in an append-only device-local intent *before* the task's first file publication, and reuses it on subsequent manual clicks for the same unchanged task.

**No live financial operation:** This remains schema-1 metadata only. Madar and Taraz remain separate; no accounting ledger posting, peer authentication, official Taraz receipt, cross-machine transport, bill or party mutation. Worktree: `D:\CoS-Test\000- Madar\madar-p2-gantt-notifications-20261107`, original HEAD `32bd8ffe`. Source is uncommitted and not deployed. Do not access real APPDATA to test.

## Exact behavior

- New pure-safe filesystem adapter `mtr_e2_send_journal.prepare_manual_send(state, taskId, expenseId, actor_scope=...)`: validates an existing saved task, computes a canonical payload hash from the **same** metadata `taraz_exchange.queue_saved_task` uses, generates one UUID, and publishes a small JSON intent in `LOCALAPPDATA/Madar-Taraz-Bridge/send-intents/<SHA256 scope>.json` via temp file+fsync+exclusive hardlink. Contains only task/project/expense identifiers, two hashes, request ID and timestamp, not selected title or financial ledger data.
- `native_app.Bridge.tarazIntegrationPrepare` enforces persisted-state/offline/role/project gates and derives actor scope locally. Client scope binds user, host URL and host TLS fingerprint; caller cannot supply arbitrary actor scope. This method **never sends**.
- Manual `src/App.jsx:sendToTaraz`: requests a reserved ID, validates response shape, then calls the preexisting queue with exactly that ID. The second click reopens the original intent without changing its hash/ID; mismatch refuses a new send. A separate history-based replay remains user-confirmed.
- `native_app.Bridge.tarazIntegrationQueue` checks a matching saved journal if one exists for the actor and task. A changed task or substituted request ID is denied even if data changes after preparation. Old history retries without a new journal retain the original file-based mismatch checks.
- Exactly one active prepared journal per actor+project+task+selected expense is supported. No automatic clearance is inferred from an unauthenticated local `reviewed` file. A later **genuinely distinct financial request/amendment** requires the future authenticated E2/E5 workflow and new human approval; the current pilot does not silently issue one.

## Failures and limitations

- Corrupt, duplicate-key, oversized or symlinked journal and mismatched payload/actor ID fail closed; unsupported filesystem hardlinks also fail rather than rewriting previous intents.
- If a crash leaves a request lock but no proposal, the sender still treats the local outcome as **unknown** and refuses risky blind resend. Directory-entry fsync on Windows, hostile local filesystem race, stale physical power-loss and external receipt authenticity remain unproven.
- Identity in this device-local prototype is not authoritative enterprise tenant identity; do not promote the actor scope into an official inter-company ACL. The native caller's project grants require host validation again at real network transport.
- An adversary with same-user access to LOCALAPPDATA can alter local files. Do not interpret this journal as an authenticated financial audit.
- No imported online provider, billable API, installation or live user data.

## Targeted evidence

- `py -3.12 -B -m unittest -q tests.test_mtr_e2_send_journal tests.test_taraz_manual_retry tests.test_taraz_exchange tests.test_taraz_review_status`: **33 tests OK**, exit 0 after journal integration.
- `py -3.12 -B -m unittest -q tests.test_mtr_e2_cross_app tests.test_mtr_e2_send_journal tests.test_taraz_manual_retry tests.test_taraz_review_status tests.test_madar_ai_provider_policy tests.test_mtr_finance_workflow_contract tests.test_radar_party_match_preview tests.test_mtr_internal_notification_policy tests.test_mtr_acceptance_matrix`: **107 tests OK**, cross-app test invoked with `MTR_TARAZ_SOURCE` pointing to isolated Taraz worktree; 0 failures. Additional E3/E5 work is ongoing, not included in that run.
- `node --test tests/general_ui_preferences.test.cjs`: **4 tests passed**; `node_modules/.bin/vite.cmd build`: PASS, with preexisting large-chunk warning; `git diff --check`: exit 0. These are source checks, not proof of installed EXE behavior.

## Release gate

Keep the new code in the isolated worktree. Before wider use require host-authenticated Taraz request/receipt query, durable idempotency and organization ACL on both sides, signed/refutable received state and version migrations, full Windows two-PC/TLS test, backup readback and rollback, manual human acceptance and separate explicit deploy approval.
