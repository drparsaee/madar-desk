# ExecPlan | Reject unauthenticated LAN POST before JSON parsing

## Baseline and decision

- Source of truth: private LocalForge `main` at `8d8118a562e596550b9a5bf65febcd39147227c6` (fetched and matched origin/main).
- Priority: MD-O02 host-side authentication and bounded unauthenticated resource consumption (`PROJECT_CONTEXT.md`, `docs/decision-inventory/DECISIONS.md`).
- Only `lan.py`, synthetic regression tests and this ExecPlan are in scope. The canonical checkout's two unrelated untracked research folders must remain untouched.

## Hypothesis / RED

`Handler.process()` reads and JSON-decodes up to 16,000,000 declared bytes for a non-login POST before it calls any token-authorized service method. An anonymous client can repeatedly submit oversized JSON to `/api/state`, `/api/attachments`, or finance endpoints without a valid bearer token, consuming server memory/CPU. Reproduce with synthetic loopback HTTP, a 70 KiB malformed/valid JSON payload and an invalid bearer token; require an authorization failure before JSON parsing. Confirm that a valid token still permits normal POST and that login remains independently capped at 64 KiB.

## Minimal repair / parity

- Preflight the bearer token via `service.account_for(token)` for non-login POST after route/framing checks but before reading/parsing the request body.
- Return the established 403 JSON error for invalid sessions; leave the existing method/body limits, route behavior and host-side ACL unchanged. A valid token is checked again at the service method as before.
- The server may close the connection on an early denial with an unread body; test the actual HTTP client response on Windows, not only a mocked handler.

## Gates

1. RED synthetic test against unmodified source.
2. Minimal source repair; focused LAN security tests and adjacent authentication/finance tests.
3. Official isolated `npm test` (Python, Vite, Node); `git diff --check` and remote freshness.
4. Only on real green gates commit and push to LocalForge main, verify remote SHA. No installed EXE, real profiles, Parsian, production host, or real two-PC tests.

## Executed source evidence (2026-11-02)

- Baseline RED: `python -B -m unittest tests.test_lan_login_resource_limits.LanLoginResourceLimits.test_unauthenticated_nonlogin_post_is_rejected_before_json_parse -v` exited 1: HTTP 400 (malformed JSON parsed) rather than required 403 (invalid bearer token rejected before parsing).
- Minimal patch: for known non-login POST endpoints, `LanService.account_for(token)` is checked before `rfile.read`/`json.loads`; early denied requests close the connection to avoid reusing unread bytes. Existing login body cap, global framing and later per-action authorization remain unchanged.
- Focused isolated smoke: 6/6 PASS for new login-resource tests and the adjacent signed Content-Length PATCH test. An earlier concurrent 38-test run had 1 Windows `ConnectionAbortedError: [WinError 10053]` in the unrelated PATCH framing fixture; its isolated rerun passed. The subsequent sequential 5-module focused rerun **38/38 PASS** in 50.315 seconds, exit 0.
- Official isolated `npm test`: exit **0**. Python **189/189 modules**, **1,733 tests reported**, **2 skipped**, **2 expected failures**, **0 unexpected failures/errors/timeouts**; Vite build PASS; Node **571/571 PASS**, **0 skipped**. The opt-in packaged EXE test was excluded by the official runner.
- `git diff --check` exit 0. Two font-license files rewritten by Vite were restored to their pre-build Git content; unrelated canonical checkout research folders were untouched. The current remote `main` was observed at `8d8118a562e596550b9a5bf65febcd39147227c6` before delivery.
- These are synthetic source checks, not physical LAN, installed EXE, real-user migration or power-loss acceptance.
