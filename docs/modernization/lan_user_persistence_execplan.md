# LAN user authorization persistence | bounded ExecPlan

## Scope and baseline

Owner decisions: durable user identities, host-enforced roles and ACL, no release claims from source tests. LocalForge `main` at `8da0f1ee33e1ec40e519368c27e2eaf08df45c10`, matching the remote ref before work. Existing untracked Trello research directories are out of scope. Only disposable synthetic users and a stub state bridge may be used. Never touch installed binaries, actual profiles or the owner's Parsian test data.

## Defect hypothesis and red test

`LanService.upsert_user` assigns `self.users[username]` before `_store_users()`. `change_password` and `reset_password` mutate the shared account dict before `_store_users()`. If filesystem persistence fails, the API reports failure while the running host can nevertheless use uncommitted account roles or credentials. Use synthetic admin/editor accounts and a mocked failing store to assert that failed persistence leaves the prior in-memory authorization and credentials intact.

## Minimum compatible correction

Build a detached candidate registry and publish it to disk before replacing the in-memory registry. Keep the existing JSON layout, session revocation behavior after success, and ACL checks. Avoid changes to normal LAN request behavior and installed host. No speculative broad refactor.

## Gates

1. Run new synthetic tests against baseline; record expected red failure.
2. Implement minimal fix and rerun adjacent LAN security tests.
3. Run isolated complete Python suite, Node/React suite and Vite build, inspect `git diff --check` and status.
4. Commit and push to LocalForge main only after all tests pass, then compare local and remote SHA. Otherwise preserve evidence and report blocker.

## Execution evidence

- Baseline source/remote `main` both `8da0f1ee33e1ec40e519368c27e2eaf08df45c10`; two unrelated untracked Trello research directories left untouched.
- RED: `python -B -m unittest tests.test_lan_user_persistence -v`, exit 1, **4/4 tests failed**. A failed synthetic user-registry write left an admin role, a ghost account or changed password in live memory despite the failed API call.
- GREEN: same test command, exit 0, **4/4 passed** after copy-on-write publication of the candidate user registry. Existing account sessions are only revoked after successful persistence.
- Adjacent isolated LAN runner: **11/11 modules passed, 80 tests, zero skips/errors/failures**.
- First integrated `npm test` **failed**, not a successful gate: an independently discovered crash-publication audit was deliberately placed in default `tests/` while still RED. Its synthetic reproduction remains documented in `docs/modernization/audits/restore_crash_publication_red.py`, outside the green regression discovery until that separate restore defect is repaired. See `restore_crash_publication_open.md`. This is an outstanding known defect, not a passing test.
- After separating that unresolved red characterization from the default regression suite, `npm test` **exit 0**: isolated Python **171/171 modules passed**, 1,635 tests reported, 2 skipped, 2 expected failures, zero unexpected failures/errors/timeouts; Vite build passed; Node/React/Playwright **530/530 passed**, zero skipped/failures.
- Scope remains source-only. Packaged EXE, real-user restore, physical LAN, power-loss durability and the owner's Parsian test database were not exercised.
- Git commit/push and remote SHA readback are separate delivery gates; only their executed output establishes delivery.
