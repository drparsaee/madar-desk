# LAN/standalone host HTTP test stabilization, 2026-11-03

## Source and scope

- Baseline: integration `0b93c50cc476dfd4abba8664f8fae6080157e47b`.
- Platform: Windows / Python 3.12.10; synthetic loopback `LanService`,
  disposable temporary directories and fake or isolated SQLite accounting.
- Changed **tests only**: `tests/test_standalone_accounting_host.py` and
  `tests/test_lan_login_resource_limits.py`.
- No change to `lan.py`, routing, session validation, finance permissions,
  native host, real APPDATA, customer data, canonical main or installer.

## Symptom and framing explanation

The prime's full-suite evidence reported intermittent
`ConnectionAbortedError [WinError 10053]` at
`test_lan_login_resource_limits.py::test_unauthenticated_nonlogin_post_is_rejected_before_json_parse`,
following a previous run that failed within `test_standalone_accounting_host.py`.
Those specific errors were **reported by the integration runner**. The
isolated baseline passed 26/26 standalone-host tests once, five login-limit
tests once and 30 independent invocations of the host's unauthenticated
POST test; this worker did **not reproduce** the abort before editing.

`lan.py` verifies HTTP framing globally and then checks the token on
non-login POST **before reading the body**. For an unauthenticated token,
the handler sets `close_connection = True` and sends JSON HTTP 403 while
the bytes the old tests transmitted remain unread. The oversized-login
handler likewise rejects the declared body length with 413 before reading
the old test's 70 KB payload. A Windows TCP reset during that early
rejection is a code-supported explanation for the intermittent abort,
**not a proven diagnosis of the observed OS-level failure**.

## Test corrections and preserved denial contracts

1. For oversized login, the test declares `Content-Length: 70000`
   without transmitting the body. It still requires HTTP 413 and that the
   expensive password verifier was never called; session storage stays empty.
2. For unauthenticated `POST /api/state`, the test declares
   `Content-Length: 70001` without transmitting body bytes. It requires
   exactly HTTP 403, the invalid-session JSON error, and no sessions.
   The server must reject before attempting a body read. If it starts
   reading that absent body, the test **fails with a timeout**.
3. For unauthenticated `POST /api/standalone-accounting`, the test sends
   a zero-body POST that must still return HTTP 403 with the exact
   invalid-session error. The fake accounting store must never be opened.
4. To keep genuine malformed-JSON validation covered separately, both
   test modules send a **complete** one-byte malformed JSON body using
   an authorized token and require HTTP 400. The accounting store must
   remain unopened in the standalone-host case.

The tests continue to fail on unexpected socket errors, timeouts,
wrong statuses, missing JSON, authentication bypass, or unintended store
access. There are no retries, generic network exception handlers, sleep
workarounds, or weakened production security checks.

## Verification

Commands:

```powershell
python -m unittest -q tests.test_standalone_accounting_host tests.test_lan_login_resource_limits
python -m unittest -q tests.test_standalone_accounting_host tests.test_lan_login_resource_limits tests.test_lan_security_framing_phase4
```

- **20 independent full two-module repetitions:** 20 passed / 0 failed;
  32 tests in each repetition = **640 individual test executions**.
- Before the fix, the isolated baseline's single whole standalone module
  returned 26/26 passes; 30 targeted baseline unauthorized POST runs
  returned 30/30 passes. The intermittent error was not reproducible on
  demand in these isolated runs.
- Combined standalone-host, login-limit and phase-4 framing regression:
  **38 tests passed / 0 failed** in a separate final command.

This validates the changed synthetic tests on this machine. It does not
establish that the Windows socket behavior is universally reproducible,
nor does it certify production LAN, end-user finance or installed EXE.
