# ExecPlan | LAN user deletion registry failure compensation

## Scope and source baseline

Baseline local `main` `18005d94fbac33710356095f59ab6dd8128c59bd` on 2026-11-02. LocalForge `origin` is configured but its readback currently fails authentication, so no remote parity or delivery is claimed. Two unrelated untracked Trello research directories remain untouched. PROJECT_CONTEXT MD-O02 and MD-D06 require host-enforced ACL and durable identity writes. No real users, Parsian data, installed EXE or operational files are used.

## Defect hypothesis and RED

`LanService.delete_user` first persists task unassignment, then persists the user registry. If `_store_users` raises, the user remains present and authenticated while previously assigned tasks have already been changed on disk. Reproduce with a synthetic bridge that accepts state saves and an injected registry-write failure. Assert task assignments, registry bytes, and the active session are unchanged after the failed deletion.

## Bounded repair

Keep a detached snapshot of task state under both existing locks and compensate a failed registry write by restoring the pre-delete state. Preserve the original exception if rollback succeeds; surface a distinct error if rollback itself fails. This is in-process compensation, **not** a crash-atomic two-file transaction. Do not overwrite unrelated state or broaden user deletion behavior.

## Gates

Run the RED test before editing production code; implement minimal change; rerun the focused LAN security tests and the repository's isolated `npm test`; inspect `git diff --check` and the exact staged paths. Commit/push to LocalForge `main` only after complete green QA and safe remote verification. If remote authentication remains broken, leave validated source changes unpushed and report the blocker without inventing delivery.

## Remaining limits

Process termination between the two file writes, rollback failure and power loss are not made crash-atomic by compensation. A durable cross-file transaction requires a separate design and acceptance gate.

## Evidence collected in this run

- RED on baseline: `python -B -m unittest tests.test_lan_delete_registry_failure -v` exited 1. The synthetic persisted task unassignment remained after an injected registry write error; expected assignee `['editor']`, observed `[]`.
- After the source repair, six adjacent LAN test modules passed: **27/27 tests**, zero failures. This was before adding a second negative rollback-failure case and disk-backed synthetic state assertions.
- The expanded focused suite `tests.test_lan_delete_registry_failure` passed **2/2**, including a real temporary JSON state file and a distinct rollback-failure signal. A rollback failure intentionally remains unrepaired; the caller is told explicitly rather than silently claiming atomicity.
- Official isolated `npm test` exit **0**: Python **174/174 modules**, **1,648 tests reported**, **2 skipped**, **2 expected failures**, **0 unexpected failures/errors/timeouts**; Vite build **PASS**; Node/React/Playwright **530/530 PASS**, zero skipped/failures. The packaged EXE and real-user migration were excluded by the runner.
- An initial `git ls-remote` failed with HTTP authentication, but a later readback succeeded and confirmed remote `main` still at baseline `18005d94fbac33710356095f59ab6dd8128c59bd`. Commit/push and post-push readback are separate delivery gates.
