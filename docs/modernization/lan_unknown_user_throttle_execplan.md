# ExecPlan | LAN unknown-username throttle reset

## Scope and decision

MD-O02 requires host-side rate limiting. Baseline local main `603673bb2e8f166dceec51084bdbb15f807726a1`. The initial remote `ls-remote` failed authentication, so remote freshness and delivery are unverified. Only `LanService.authenticate`, synthetic tests and this plan are in scope. Do not touch real profiles, installed EXE, Parsian, financial data, or unrelated untracked research.

## Hypothesis and red test

An IP can make five failed logins to arbitrary nonexistent usernames, log in to a known valid low-privilege account to clear `self.failed[ip]`, and continue guessing new usernames. The existing per-account throttle tracks only existing accounts and does not protect the unknown-username path. Reproduce using disposable accounts, a documentation-only IP, and a frozen clock. Require a sixth unknown-name failure to exhaust the IP's unknown-name budget even after a valid login, while a separate successful session remains valid and expiry at 120 seconds works.

## Minimal compatible change

Retain the existing global IP budget and per-existing-account budget. Add a bounded per-IP unknown-username failure budget, not cleared by a successful login to any account. Avoid per-unknown-username entries. Preserve existing error strings, session issuance and normal same-account success semantics. Do not add persistent user data or change credentials.

## Gates

1. Run synthetic RED before code changes and record result.
2. Implement minimal change; run targeted LAN and ACL suites.
3. Run official `npm test` isolated Python, Vite build and Node/React; inspect diff and Git status.
4. Verify remote main; commit and push only after green gates and remote freshness. Compare remote SHA to local SHA. If authentication remains unavailable, do not claim delivery.

## Limitations

This is source-level throttle characterization, not proof of security under distributed attackers, multiple host processes, physical LAN, installed EXE or real accounts.

## Executed evidence (2026-11-02)

- Initial `git ls-remote` failed with authentication error. A fresh retry succeeded and matched local `603673bb2e8f166dceec51084bdbb15f807726a1`; the failure was transient.
- RED: `python -B -m unittest tests.test_lan_account_lockout -v` exited 1: 4 tests run, 1 failure in the new unknown-username-budget test. A valid viewer login cleared the shared IP counter and let a sixth unknown username attempt proceed without locking the IP.
- GREEN: `python -B -m unittest tests.test_lan_account_lockout tests.test_lan_user_persistence -q` exited 0, 9/9 tests passed. The additional counter is per IP and counts only nonexistent usernames; no per-guess memory entries are created.
- Focused isolated LAN suite: 11/11 modules passed, 82 tests reported, no skips, failures or errors. Report written to a temporary directory outside Git.
- Official `npm test` exited 0: isolated Python 172/172 modules, 1,643 tests reported, 2 skips and 2 expected failures, zero unexpected failures/errors/timeouts; Vite production build passed; Node/React/Playwright 530/530 passed with zero skips/failures. Packaged EXE and real-user migration explicitly excluded.
- `git diff --check` exited 0 (Windows line-ending warning only). No real profiles, financial data or operational versions were used.
- Delivery SHA and remote readback must be recorded from actual Git output, not inferred from test success.
