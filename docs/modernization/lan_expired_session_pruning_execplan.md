# ExecPlan | Retire expired LAN sessions during successful authentication

## Decision, baseline and safety boundary

- LocalForge private `main` at `45f3a596abe1496147a0e2b2e453b8a93de80624`, matched `origin/main` before starting. The canonical checkout has two unrelated untracked Trello research directories; leave them untouched.
- `PROJECT_CONTEXT.md` MD-O02 and `docs/decision-inventory/DECISIONS.md` require secure host-side authentication and bounded resource usage. `LanService.account_for` only deletes an expired token when that exact token is presented. `authenticate` creates fresh sessions without retiring other expired tokens, so abandoned sessions can accumulate for the lifetime of a LAN host.
- Scope: `lan.py`, one synthetic regression, this ExecPlan. No operational profiles, Parsian backups, installed EXE, live LAN service or user data.

## Test-first acceptance

1. Create an owner under a temporary users.json and freeze a synthetic clock. Issue an expired token, a still-live token, then a fresh successful login. RED: the expired token remains in `service.sessions` while no client presents it.
2. At successful login, prune entries with expiry at or before the current time before issuing the new token. Preserve all unexpired sessions, the 12-hour TTL, failed-login budgets, password verification and role ACL. Never prune sessions on a failed login.
3. Run the focused LAN authentication and session regression, then official isolated `npm test` (Python, Vite and Node). Check `git diff --check`, local/remote SHA and worktree status; only push after actual green gates.

## Limits

This bounds *stale* session retention on future successful logins, not the count of concurrently valid sessions. It is not a deployed-host load test, real-user login acceptance or proof against all resource-exhaustion attacks.

## Evidence

- RED at baseline `45f3a596`: `python -B -m unittest tests.test_lan_session_expiry_pruning -v` exited 1. An expired token remained in the in-memory `sessions` dictionary after a new successful login (1 assertion failure).
- Initial GREEN before the extra failed-login assertion: 40/40 tests passed in 59.297s across session pruning, account lockout, login resource limits, user persistence and HTTP LAN tests. Final focused/full gates still pending.
- Two complete 5-worker Python audits and one serial 1-worker audit each reported 189/190 modules PASS, 1 error in `test_lan_security_framing_phase4.py`, with `[WinError 10053]` from `http.client.getresponse()` after malformed requests containing unread bodies. The failed case varied between missing HTTP/1.1 Host and signed Content-Length; the isolated 6/6 framing module passed. This is an existing Windows TCP delivery assumption in a synthetic test, not an observed authentication bypass. The test now accepts only the documented Windows connection abort/reset **or** HTTP 400, and additionally requires zero sessions and a healthy responding host after rejection. No runtime framing validation was weakened. Rerun all gates after this harness correction.
