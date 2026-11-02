# ExecPlan | LAN user deletion must not mutate live task cache before save

## Baseline and authorization

LocalForge `main` and checkout both at `6f1ae6f26efc20cbac5fcc6fc5393063c324f938` at start, with only two unrelated untracked Trello research directories. `PROJECT_CONTEXT.md` MD-O02 / MD-D06 and `docs/decision-inventory/DECISIONS.md` require host-side authorization and durable writes. No installed EXE, actual profiles, Parsian database or finance records are involved.

## Reproduction

`native_app.getState()` assigns and returns `self.state`, a live mutable object. `LanService.delete_user()` modified `state['tasks']` before calling `bridge.saveState()`. If persistence raises, the live host cache has already lost the deleted user's assignments even though deletion itself failed. Synthetic bridge `getState()` deliberately returns the same object; `saveState()` raises `OSError`. RED command: `python -B -m unittest tests.test_lan_delete_state_atomicity -v`, exit 1, 1/1 failed because the cached assignees became `[]` instead of `['editor']`.

## Minimal repair and acceptance

Deep-copy the returned bridge state before modifying task assignments, preserving existing deletion order and ACL behavior. The regression must verify task cache, registry bytes, user session and save attempt after an injected failure. Run adjacent LAN tests and the official isolated `npm test`, check diff, commit and push only after all gates pass, then compare local and remote SHA.

## Explicit limitation

This fixes a proven in-process failure atomicity defect. It does not provide crash-atomicity across the task state and separate LAN registry files when state save succeeds but registry save fails, nor prove physical power-loss durability or installed-host behavior. That separate cross-file transaction remains open and should not be described as repaired.

## Executed source QA (2026-11-02)

- RED baseline: one synthetic regression failed as expected, demonstrating live task assignments changed from `['editor']` to `[]` despite an injected `OSError` in `saveState()`.
- GREEN after deep-copy: focused LAN regression set **26/26 passed** (`tests.test_lan_delete_state_atomicity`, `test_lan_user_persistence`, `test_lan_account_lockout`, `test_lan_display_roles`, `test_lan_security_framing_phase4`).
- `npm test` exit **0**: isolated Python **173/173 modules passed**, **1,646 tests reported**, **2 skipped**, **2 expected failures**, **zero unexpected failures/errors/timeouts**. Vite build **PASS**. Node/React **530/530 passed**.
- `git diff --check` exit **0**; baseline remote `main` SHA matched local `6f1ae6f26efc20cbac5fcc6fc5393063c324f938` before delivery. The packaged EXE and real LAN were not tested.
- Commit, push and remote readback must be verified separately; source QA is not a release acceptance.
