# ExecPlan | LAN coworker directory must exclude zero-grant identities

## Purpose, decision and exclusions

- Baseline: private LocalForge `main` at `9b7967ec18e9c3a6d1e59a2b902d410f82a06b25`, confirmed equal to `origin/main` after fetch on 2026-11-02.
- `PROJECT_CONTEXT.md` MD-O02 and `DECISIONS.md` require host-enforced user visibility and scope. A coworker directory must not disclose identities with no common project to ordinary viewers/editors.
- Scope: `lan.py`, `tests/test_lan_profile_zero_grant_directory.py`, this document. Preserve the two unrelated untracked `research/trello-design-system/` directories.
- No real account, profile, LAN host, Parsian database, installed EXE, release or operational data may be read or changed.

## Existing behavior and RED characterization

- `LanService.list_profiles` returns self for every account and a full directory for administrators. A non-admin with `projects=[]` already sees only self.
- A non-admin with `projects=None` (access to all projects) currently enters the `shared=None` branch for a coworker with `projects=[]`. That coworker is returned even though it has **zero** projects in common. The response contains profile metadata, which is unnecessary disclosure.
- Reproduce with a disposable user-registry file and a synthetic bridge exposing one fake project, three synthetic identities (admin, unrestricted viewer, zero-grant viewer), and no real network requests. Require unrestricted viewer not to see zero-grant coworker, while administrator may still manage that account and a scoped coworker remains visible.

## Bounded change and parity contract

1. Add a synthetic regression test and execute it against the unmodified `lan.py`; retain observed failure.
2. In the non-admin coworker loop, skip accounts whose project scope is an explicit empty list. Keep self and admin directory behavior unchanged; preserve existing intersection/redaction rules for all other scopes.
3. Run targeted directory/role/LAN tests and the repository's isolated `npm test` (Python module subprocesses, Vite, Node). Review diff, syntax, staging and Git remote freshness.
4. Only after all required source checks pass, commit the three scoped files and push a fast-forward to private LocalForge `main`; verify remote SHA independently. This is not a Windows release.

## Progress and evidence

- `VERIFIED RED`: on unchanged `lan.py`, `python -B -m unittest tests.test_lan_profile_zero_grant_directory -v` exited **1**, one test failed because `zero-grants` was returned to `unrestricted`. The test used a temporary synthetic user registry and synthetic project only.
- `IMPLEMENTED`: skip explicit empty coworker project scope only for non-admin directory requests; preserve self, admin and normal shared-project entries.
- `VERIFIED focused`: isolated-profile `python -B -m unittest tests.test_lan_profile_zero_grant_directory tests.test_role_profiles tests.test_lan tests.test_lan_display_roles tests.test_profile_cache_acl tests.test_lan_user_persistence -q` exited **0**, **46/46 passed** in 63.803 seconds.
- `VERIFIED syntax/diff`: `python -B -m py_compile lan.py tests/test_lan_profile_zero_grant_directory.py` and `git diff --check` exited 0.
- `VERIFIED full source gate`: `npm test` exited **0** using the repository's disposable-profile runner. Python **179/179 executed modules passed**, **1,660 tests reported**, **2 skipped**, **2 expected failures**, **0 unexpected failures/errors/timeouts**; Vite build PASS; Node/React/Playwright **530/530 passed**, 0 failed/skipped. `test_packaged_madar_host_exe.py` was deliberately excluded by the official runner.
- `VERIFIED staged scope`: reviewed the staged diff of exactly three intended files (`lan.py`, this ExecPlan and the synthetic regression); `git diff --cached --check` exited 0. Commit and LocalForge push must be verified separately from Git after execution. Never treat excluded packaged-EXE or real LAN acceptance as passed.

## Surprises, rollback and acceptance limits

- The unrestricted viewer's `projects=None` is an intentional **all-project** grant, not an administrator role. A zero-grant coworker has no shared project with that viewer, even though the viewer can access every *existing* project.
- A source-only revert of this scoped change is possible. This does not establish real two-PC permissions, packaged EXE acceptance, full accounting migration or operational release readiness.
