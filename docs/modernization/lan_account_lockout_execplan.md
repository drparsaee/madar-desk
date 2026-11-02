# LAN account lockout isolation | bounded ExecPlan

## Purpose / decision / exclusions

- Owner decision: MD-O02 (host-side authentication and throttling), as tracked in `PROJECT_CONTEXT.md` and `docs/modernization/p0_audit_followups_20261101.md`.
- Baseline: LocalForge `main` at `271b8c1e2f4096bd9f3ed7688ab32ac9992d0702`, checkout `D:\CoS-Test\madar-desk`.
- Scope: `lan.py` `LanService.authenticate`, synthetic LAN security regression tests, and this plan. No real accounts, credentials, Parsian data, EXEs, installer, or service configuration.
- Existing untracked Trello research directories are unrelated and must remain untouched.

## Existing behavior / overview

`LanService.authenticate` holds `self.lock` and uses `self.failed[ip]` for six failures / 120 seconds. An arbitrary valid login at that IP removes the IP counter. Existing sessions remain usable after a lockout. This means a successful lower-privilege login can clear the failed-login budget accumulated while guessing a different account's password. The service's user registry is loaded from `users_path`; this plan uses only disposable temporary files and synthetic accounts.

## Design / parity contract

Preserve the existing IP-level failure budget and valid-login token/session response. Add a second, in-memory failure budget keyed by `(ip, existing_username)` so a successful login to a *different* account cannot erase the target account's six-failure/120-second protection. A successful login to the same account can clear its own failure history before lockout; a locked account must wait for its window to expire even with the correct password. Do not reveal whether a username exists in error messages. Unknown-user attempts still count against the IP budget, without creating unbounded per-username records. The account budget resets after its 120-second window. No persistent schema or money-policy changes.

## Plan of work / progress

1. **VERIFIED:** Added synthetic red test: five failed admin logins, successful viewer login at same IP, sixth failed admin login, then correct admin credentials rejected; independent IP and existing session remain usable. Baseline result: 3 tests, 1 expected failure, exit 1.
2. **VERIFIED:** Added an in-memory `(ip, existing_username)` failure budget while retaining global IP throttle and existing public error contract; unknown usernames do not create per-account entries.
3. **VERIFIED:** Targeted regression: 3/3 new tests passed; 10/10 LAN modules passed, 76 tests reported, 0 failures, 0 skips. Existing account success before lockout clears its own budget; expiry after 120 seconds permits login.
4. **VERIFIED (source validation):** Full isolated Python runner: 170/170 modules passed, 1,624 tests reported, 2 skips, 2 expected failures, 0 unexpected failures/errors/timeouts. Packaged-EXE test intentionally excluded by runner. Node suite: 530/530 passed with isolated Playwright headless-shell QA adapter (see below). `npm run build` succeeded; Python AST parsing and `git diff --check` succeeded.
5. **DELIVERY GATE:** Review exact staged paths, verify remote SHA, commit and push to LocalForge `main` only after green validation. Git history and the remote ref, not this pre-commit plan, are authoritative for the resulting SHA and push status. No deployment.

## Surprises / decision log

- 2026-11-01: A previous worker's reported reproduction is a lead, not a verified result in this run.
- At initial inspection `git ls-remote origin refs/heads/main` failed with `remote: Failed to authenticate user`; remote synchronization and any push must be independently verified before claiming delivery.
- A later `git ls-remote origin refs/heads/main` succeeded and matched the baseline SHA; initial authentication failure was transient.
- Initial direct Node suite: 512/530 passed, 18 browser-launch failures because the installed Google Chrome rejected Playwright remote debugging despite a temporary profile. These are recorded as **failed initial checks**, not rewritten as passes. A disposable test-process-only `NODE_OPTIONS=--require=<temp shim>` adapter substituted the already installed Playwright Chromium headless shell for the hardcoded system Chrome executable. A standalone browser probe and a browser test passed before the complete unchanged 94-file Node test suite passed 530/530. The adapter was never added to source, and no real browser profile was opened. This validates source/UI against Playwright Chromium, **not** against the locally policy-blocked Google Chrome executable.

## Validation / acceptance / rollback

Red-before and green-after are mandatory. Tests use `tempfile.TemporaryDirectory`, synthetic usernames/passwords, and isolated APPDATA/LOCALAPPDATA/TEMP/HOME/USERPROFILE. No production host or installed executable is started. Rollback is the scoped source commit reversal, not a live database rollback. GUI, two-machine LAN, installed EXE, and real-user acceptance remain open regardless of source-level success.

Executed commands: `python -m unittest discover -s tests -p test_lan_account_lockout.py -v` (red and green, disposable profile), `python -B tools/modernization_python_suite.py --workers 3 --timeout 150 --pattern 'test_lan*.py' --report <temp>`, `python -B tools/modernization_python_suite.py --workers 4 --timeout 150 --report <temp>`, `node --test --test-concurrency=1 <all 94 tests/*.test.cjs>` (direct system Chrome failed, isolated Playwright headless-shell adapter passed), `npm run build`, AST parsing, `git diff --check`. Test reports/logs are temporary outside Git, not production records.
