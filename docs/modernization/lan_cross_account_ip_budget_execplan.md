# ExecPlan | LAN known-account IP budget cannot be reset by another login

## Scope and baseline

Baseline LocalForge `main` is `e526a20495dad09b7d339a7608006da7cdd37602`; a fresh `git ls-remote` retry matched this SHA after a transient authentication error. Two untracked Trello research directories are unrelated and must remain untouched. This addresses host-side LAN authentication rate limiting (PROJECT_CONTEXT MD-O02, DECISIONS MD-D06). Only `lan.py`, `tests/test_lan_account_lockout.py`, and this plan may change. Use synthetic identities and an RFC 5737 IP; no real profiles, Parsian, EXE or operational data.

## Hypothesis and RED

`LanService.authenticate` clears the shared IP failure counter on *any* valid account login. Per-account counters stop repeated guesses against one known account, and the separate unknown-name counter protects nonexistent names, but neither prevents password spraying across multiple *existing* usernames after an attacker logs in to one known low-privilege account. Reproduce five failed admin guesses, a valid viewer login, then an additional failed editor guess; require the global IP budget to lock further login until the 120-second window ends.

## Minimal compatible repair

Track only the SHA-256 digest of the one username responsible for all recent IP failures, or a mixed-target sentinel. A successful login clears the shared IP counter only when all its failures were against that same authenticated username; a different account cannot erase those failures. Keep the existing per-account and unknown-name budgets, 120-second expiry, token behavior, and the documented successful *same-target* login reset. Do not retain arbitrary attacker-supplied usernames in this new tracking map.

## Gates

1. Run new synthetic regression RED against baseline.
2. Apply minimal change; run focused LAN/account security tests and full isolated `npm test`.
3. Review exact diff and remote freshness; commit/push only on green, then compare local and remote SHA.
4. Installed EXE, actual multi-device LAN and distributed-source brute force remain unverified.

## Executed source-only evidence (2026-11-02)

- Initial `git ls-remote origin refs/heads/main` returned an authentication error; retry succeeded and matched local baseline `e526a20495dad09b7d339a7608006da7cdd37602`. Only two unrelated Trello research directories were untracked.
- RED: `python -B -m unittest tests.test_lan_account_lockout.LanAccountLockoutTests.test_known_account_spray_cannot_reset_ip_budget_via_other_login -v` exited 1 with one expected assertion failure: a valid viewer login erased five failed admin guesses and a later editor login was allowed.
- GREEN: `python -B -m unittest tests.test_lan_account_lockout tests.test_lan_user_persistence tests.test_lan_display_roles tests.test_lan_security_framing_phase4 -q` exited 0, **26/26 tests passed**. Existing same-account reset, unknown-name throttle and 120-second expiry tests remain green.
- Official `npm test` returned exit **0**. Its isolated Python phase reported **175/175 modules**, **1,651 tests**, **2 skips**, **2 expected failures**, zero unexpected failures/errors/timeouts. Vite build reported PASS. The Node phase ran and the complete runner exited 0, which requires its strict Node pass/skip/count check; its exact numeric summary was not retained in the observed tool output, so no new Node count is claimed here.
- `git diff --check` exited 0 (only Windows line-ending warnings); pre-commit remote `main` still matched baseline. No installed EXE, real LAN, Parsian, operational profiles or databases were touched.
- Commit/push and post-push remote SHA must be verified separately; the source QA result is not a deployment acceptance.
