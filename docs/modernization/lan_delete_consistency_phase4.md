# ExecPlan | LAN user deletion consistency (phase 4, 2026-11-02)

## Source baseline and user-data boundary

- Started from `main` commit `10a28b8629ea285a3ac078717dc8622d0cb62ffb` in the isolated `modernization/phase4-20261102` branch/worktree.
- User data and the installed executable are never inputs to these tests. Fake users, sessions and card assignments are held in a temporary local test registry.
- Deleting a LAN account must remove that user's task assignments and revoke the deleted user's active sessions **only after** the operation has succeeded. Existing task metadata and other assignees must be preserved.

## Reproduction before changes

`LanService.delete_user()` saved unassigned cards, mutated `self.users` and revoked sessions before calling `_store_users`. A synthetic `_store_users` failure left the returned operation failed, but the card had already lost the assignment. The new RED test exercised this exact failure: **3 tests, 1 failed** (`editor` was removed from the card even though the registry write failed), while the pre-existing happy path and card-write-failure behaviors passed.

A second synthetic RED test passed an unhashable `username` to the delete operation. Before input validation, `if username not in self.users` raised an uncaught `TypeError` instead of the established controlled `ValueError` path. **1 test ran, with 3 subtest errors**.

## Bounded implementation

1. Acquire LAN identity and bridge locks in the established identity-then-state order. Deep-copy the current card state instead of modifying an object returned by `getState()` in place.
2. Construct a candidate user registry without the deleted user. Persist it first. A failed registry write now leaves assignments, in-memory users and sessions unchanged.
3. Save the updated task state only after identity persistence. If this second step throws, try to restore the previous user registry and re-raise the exception. Publish `self.users` and revoke the deleted user's sessions only after the task save succeeds.
4. Require a string `username` before dictionary lookup. The existing error message and successful delete semantics are retained.

## Evidence and explicit limitation

- The targeted persistence test module passed **10/10** after both patches, with synthetic disk-write failure, card-write failure, an aliasing `getState` reference, invalid input, and successful deletion / session revocation.
- **Pre-patch complete source baseline:** official `npm test` exit 0, Python 172/172 modules with 1,643 tests reported (2 skipped, 2 expected failures, zero unexpected failures/errors/timeouts); Vite build PASS, serial Node/React/Playwright 530/530 PASS, 0 skipped. Packaged EXE excluded.
- **Post-patch official full gate:** `npm test` exit **0**, Python **172/172 modules, 1,648 tests** (2 skipped, 2 expected failures, zero unexpected failures/errors/timeouts), Vite build PASS, serial Node/React/Playwright **530/530 PASS** (0 skipped). These results were executed on the branch worktree with only synthetic isolated app profiles; no installed EXE was changed.
- `git diff --check` returned exit code 0; LocalForge `main` was read back via `ls-remote` at the exact starting SHA before branch publication. Commit/push verification is a separate gate.
- This is **ordinary exception-path compensation**, not an atomic distributed transaction across the user registry and card store. A power loss, abrupt process termination between both writes, a failed compensating registry write, or a storage failure after a partial card save remains an open crash-consistency risk. A durable journal / unified transaction boundary and hard-stop recovery validation are needed for operational release sign-off.
- Full isolated Python, Vite and serial Node/Chromium suites must be rerun on the final source and recorded separately. Commit, LocalForge push and installed EXE are distinct gates.
