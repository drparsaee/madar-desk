# LAN phase-4 signed Content-Length test stability, 2026-11-03

## Scope and environment

- Source baseline: official integrated commit `90e331bd1b92c650de7a703af5618841944c59dc`.
- Windows / Python 3.12.10, loopback-only disposable `LanService` and synthetic owner.
- Authorized change: `tests/test_lan_security_framing_phase4.py` only. The production LAN server and security policy were not changed.
- Reported symptom: intermittent `ConnectionAbortedError: [WinError 10053]` in
  `test_patch_rejects_signed_content_length_before_routing`.

## Investigation

The original test sent both `Content-Length: +2` and two bytes of body. In
`lan.py`, `Handler.process` rejects that signed header with a JSON 400 at the
global HTTP framing validation, before routing or reading the body. An unread
request body when the server exits the request is a plausible cause of a TCP
abort/reset on Windows, which can make `HTTPConnection.getresponse()` fail
even though the application attempted the correct 400 response.

This is a **code-supported hypothesis, not a reproduced or independently
proven cause** of the reported Windows error. On this workstation the unchanged
baseline passed two whole-module runs (6 tests each) and 20 independent
single-test invocations; the reported `WinError 10053` did not recur.

## Minimal test correction and security assertions

The PATCH test now sends the same invalid `Content-Length: +2` header with
**no request-body bytes**. The parser must still reject the signed header
before dispatch, and the test now asserts all of:

1. HTTP status is 400.
2. JSON body equals `{"error": "طول درخواست نامعتبر است."}`.
3. The service created no login sessions.

The independent POST-with-signed-length test, missing Host test, absolute URI,
network-path rejection and valid login/GET compatibility tests remain unchanged.
On a hypothetical framing-regression allowing `+2`, the PATCH route would
fall through to a different response (405); the exact 400/error assertion
would fail. No security bypass, exception suppression, connection-error
catch-all or relaxation of production header validation was introduced.

## Validation evidence

Run from this branch's isolated worktree:

```powershell
python -m unittest -q tests.test_lan_security_framing_phase4.LanOriginAndFramingTests.test_patch_rejects_signed_content_length_before_routing
python -m unittest discover -s tests -p test_lan_security_framing_phase4.py -q
```

- **After change:** 25 separate single-test executions, **25 passed / 0 failed**.
- **After change:** 5 full module executions, **5 passed / 0 failed**, each with 6 tests (30 individual test cases).
- **After change:** adjacent LAN login-resource-limit tests together with the
  framing module: **11 passed / 0 failed** in one execution.
- All runs used a new disposable per-test loopback server and synthetic users.
- `pytest` was unavailable (`No module named pytest`), so Python's
  built-in `unittest` runner was used.

These results establish repeated passing behavior on this machine, not proof
that every Windows networking/security configuration is free of resets.
No main branch, real LAN listener, APPDATA, financial data or installer was changed.
