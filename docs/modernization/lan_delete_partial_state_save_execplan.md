# ExecPlan | LAN deletion when state save commits and then raises

## Source and boundary

LocalForge `main` baseline `a91f29544415833fdc7e94774e8c2c71a8b309b3`. The two untracked Trello research directories are unrelated and excluded. Source-only synthetic regression for MD-O05/MD-O15 data consistency. Do not access real profiles, Parsian data, installed EXEs, or operational services.

## Hypothesis and RED

`LanService.delete_user` calls `bridge.saveState(state)` outside its registry-failure compensation block. A state writer can durably publish a new state and then raise (e.g., post-commit notification failure). The delete then aborts, leaving the identity and session active but removing its task assignments on disk. A synthetic bridge writes disposable JSON and raises immediately after the first committed write. Require the prior assignments, registry bytes and active session to remain unchanged after the error.

## Bounded repair

If the initial state save raises, inspect the host's persisted state under both existing locks. If it is unchanged, propagate the original error without a second write. If it exactly matches the attempted unassignment, restore the detached prior state. Fail closed for an unexpected revision or unreadable state instead of overwriting unrelated work. Preserve the original failure when compensation succeeds; explicitly surface a rollback-failure error if compensation fails. Do not claim crash-atomicity, and do not change successful deletion semantics.

## Validation gates

Run RED before source change, focused LAN tests, official isolated `npm test`, diff and staged-path checks. Only then commit/push to LocalForge `main` and independently compare remote SHA. Real power loss, installed host and network acceptance remain separate gates.

## Executed evidence (2026-11-02)

- Fresh `main` and LocalForge remote baseline both `a91f29544415833fdc7e94774e8c2c71a8b309b3`; two unrelated untracked Trello research folders excluded.
- RED before editing `lan.py`: two synthetic tests yielded one assertion failure (assignments remained removed after a post-commit exception) and one unexpected OSError where explicit rollback-failure reporting was required; process exit 1.
- First adjacent run after a naive unconditional rollback failed: existing pre-commit failure fixture expected one write attempt and the original OSError. The repair now inspects the persisted state before deciding whether rollback is needed.
- GREEN focused: five adjacent modules including new tests, **14/14 passed**, exit 0; `git diff --check` exit 0.
- Official isolated `npm test`: exit **0**. Python **176/176 modules**, **1,653 tests reported**, 2 skipped, 2 expected failures, 0 unexpected failures/errors/timeouts. Vite build PASS; Node **530/530 passed**, 0 skipped/failures. Packaged EXE and real-user migration excluded.
- Source-only compensation is not crash-atomic across account registry and task-state files; an unreadable or unexpected state revision fails closed. Real LAN, installed EXE and physical power-loss durability remain unverified.
