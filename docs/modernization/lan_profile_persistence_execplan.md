# ExecPlan | LAN profile persistence after failed disk write

## Baseline and decision

Local `main` at `f307a89fad93eb6b85a4cd3272a5f96b6f20ec56`; remote freshness is **unverified** because initial `git ls-remote` returned an authentication failure. This bounded source-only task follows MD-O02 and the earlier `lan_user_persistence_execplan.md`: never publish uncommitted identity state in memory. The only two pre-existing untracked Trello research directories are out of scope. Do not touch real user profiles, installed executables, finance or Parsian data.

## Defect and red test

`LanService.update_profile` modifies the shared account dictionary in place before `_store_users()`. A synthetic failure of the registry write raises to the caller while the current session sees the uncommitted profile. Add a disposable-directory regression test that checks both in-memory identity and on-disk bytes after a forced store error. Execute against baseline to establish RED.

## Minimal fix

Construct a detached user account and candidate registry, persist it first using the existing `_store_users(updated)` path, then replace `self.users` under `self.lock`. Preserve existing ACL, validation, sessions and JSON format.

## Verification and delivery

Run RED, apply minimal fix, run focused LAN suite and official safe `npm test` (isolated Python, build, Node). Inspect diff and worktree. Commit and push to LocalForge `main` **only** after full tests pass and remote synchronization is verified. Otherwise keep source changes uncommitted and document the exact blocker. No installed EXE, real LAN or customer data acceptance is implied.

## Executed evidence

- Baseline RED: `python -B -m unittest tests.test_lan_user_persistence -v` exit 1, 5 tests run, one expected *observed* assertion failure: after a simulated disk-write error, the authenticated admin profile displayed an uncommitted `displayName`.
- After copy-on-write change, same module exit 0, 5/5 passed. The synthetic fixture also verified unchanged registry bytes after failed persistence.
- Focused LAN isolated runner: 11/11 modules passed, 81 tests, zero skipped, failed or errored; report generated under temporary profile location.
- Remote initially returned an authentication error; a later read-only `git ls-remote` succeeded and matched baseline `f307a89fad93eb6b85a4cd3272a5f96b6f20ec56`. Delivery requires a fresh readback after push.
- Official `npm test` exited 0: isolated Python 172/172 modules, 1,642 tests reported, 2 skips, 2 expected failures, no unexpected failures/errors/timeouts; Vite production build passed; Node 530/530 passed with no skips or failures. Packaged EXE and real-user migration were explicitly excluded by this runner.
- `git diff --check` exited 0; initial warning about Windows LF/CRLF conversion in test working copy is not a test failure. Unrelated untracked Trello research directories remain untouched.
