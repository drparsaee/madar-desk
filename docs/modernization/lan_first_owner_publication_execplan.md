# ExecPlan | First-owner identity registry postpublication failure

## Scope and source

Canonical private LocalForge `main` at `49805bbdbaf3173caf13cf7fdc8ff3365041e62a` (fetched and compared with origin/main, 2026-11-02). The unrelated untracked Trello research folders remain untouched. `PROJECT_CONTEXT.md` MD-D06 / MD-O02 and the managed roles decisions require durable host-side identity and ACL. Only `lan.py`, synthetic tests and this plan are in scope. Never access installed EXE, Parsian, operational data or actual user profiles.

## RED hypothesis

`setup_owner` calls `_store_users` directly rather than the compensating `_publish_users` used by later identity mutations. If the first owner registry is atomically published but a subsequent filesystem step raises, setup reports failure, live memory remains empty and restart loads an admin that the caller believes was not created. A disposable, empty registry with injected postpublication failure must reproduce this inconsistency. An unexpected foreign revision must not be overwritten.

## Minimal correction

Use `_publish_users` for first owner creation. Extend its rollback for an originally absent registry: remove the exact candidate file rather than replacing it with an empty JSON registry. Preserve normal first-owner success and refusal to create a second owner. Keep in-process error compensation distinct from power-loss or cross-process atomicity.

## Validation gates

Run red tests on untouched implementation, then focused and adjacent LAN/identity tests and the official isolated `npm test` gate (Python, Node and Vite). Verify syntax and diff. Commit/push only on green, with fresh remote SHA verification. Installed Windows EXE, real LAN, abrupt power loss and customer acceptance remain unverified.

## Observed evidence (2026-11-02)

- **RED:** Four disposable first-owner tests on untouched `lan.py` exited 1: one assertion failure (an owner survived the reported failure on disk), one unexpected `OSError` (foreign registry revision not identified), and two passing parity tests.
- **GREEN focused:** 16 tests across first-owner, existing identity postpublication and registry-persistence modules exited 0. The first broader ad-hoc six-module command was **not** green: one mistyped nonexistent test module and a Windows loopback connection abort in an unrelated raw-HTTP test caused two errors. This failed command is not counted as a successful gate.
- **GREEN complete source QA:** Official `npm test` exited 0: 183/183 executed Python modules, 1,681 tests, two skipped, two expected failures and zero unexpected errors/failures/timeouts. Vite build passed. Node 540/540 passed with no skipped or failed tests. Packaged EXE intentionally excluded.
- `python -B -m py_compile` and `git diff --check` exited 0. Only a synthetic first-owner test, this ExecPlan and the narrow `lan.py` fix are in scope.
