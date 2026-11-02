# ExecPlan | LAN deletion after registry write commits then raises

## Baseline and contract

LocalForge `main` and local HEAD `4ae52a0b9fd70fc4c260f1cddc812242bbf973e3` at start. Two unrelated untracked Trello research directories must remain untouched. PROJECT_CONTEXT MD-O02 and MD-D06 require consistent host-side identity and access. Only synthetic users and temporary task-state files are in scope. Do not touch real profiles, Parsian data, installed EXEs or operational services.

## RED hypothesis

`LanService.delete_user` saves task unassignment, then `_store_users(remaining_users)`. A registry writer can atomically publish the deletion and raise afterward. Existing exception handling restores task assignments but leaves the deleted registry on disk, while `self.users` and the live session still expose the user. A fresh service loses the user. Inject this failure in a temporary registry and assert both persisted files, memory and session remain consistent. Also require unexpected foreign registry revisions to be preserved, not overwritten.

## Bounded repair

On registry-save exception under both existing locks, inspect the actual persisted registry. If unchanged, perform only the existing task-state compensation. If it exactly matches the intended deletion, restore the prior registry before task-state compensation. If unreadable or different, fail closed without overwriting an unknown revision. If registry compensation fails, report that failure explicitly. Keep successful deletion semantics and do not claim cross-file crash atomicity.

## Validation gates

Run the new RED before source edit, adjacent LAN suites, official isolated `npm test`, `git diff --check`, staged-path review, then commit/push to LocalForge `main` only if all gates pass. Verify remote SHA independently. Real LAN, installed EXE, power-loss durability and migration remain separate acceptance gates.

## Executed source evidence (2026-11-02)

- Local HEAD and LocalForge `main` both `4ae52a0b9fd70fc4c260f1cddc812242bbf973e3` before changes; only the two pre-existing untracked Trello research directories were unrelated.
- RED `python -B -m unittest tests.test_lan_delete_partial_registry_save -v`: exit 1, one assertion failure (registry compensation never attempted) and one unexpected OSError (foreign revision not reported). All test records were synthetic and temporary.
- GREEN: new regression module 3/3 passed, including explicit registry-rollback failure; adjacent LAN modules 34/34 passed before the third regression was added. `git diff --check` exit 0.
- Official isolated `npm test`: exit 0. Python 177/177 executed modules, 1,656 reported tests, 2 skipped, 2 expected failures, no unexpected errors/failures/timeouts. Vite build PASS. Node 530/530 passed, zero skipped/failures. The runner expressly excludes installed EXE and real-user migration.
- In-process compensation cannot make the two files crash-atomic; foreign/unreadable registry revisions fail closed. Real LAN and physical power-loss durability remain unverified.
