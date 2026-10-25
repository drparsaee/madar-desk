# Madar Desk v1: LAN acceptance record

## Test boundary and execution

- **Scope:** Server-side LAN behavior in `lan.py`, exercised through real HTTP(S) socket listeners, plus the existing desktop `native_app.Bridge` LAN/offline client interface (read-only use, no changes to that file).
- **Environment:** Two simultaneous `LanService` hosts listening on distinct ephemeral `127.0.0.1` ports in **one Windows/Python process**. Each host owns a separate real `Bridge` and user store. Additional distinct client `Bridge` instances test reconnect and offline persistence.
- **Data isolation:** All test instances use distinct directories beneath `tempfile.TemporaryDirectory` with a patched `APPDATA` and per-instance patched `native_app.datadir` during construction. Tests tear down both listeners before removing temporary files. Real user APPDATA and existing accounts are not used.
- **Transport:** Host A uses HTTP to exercise the legacy transport's compatibility/ACL contract. Host B uses HTTPS with the public **test-only certificate and key fixture** already present in `tests/test_lan_tls.py`; these credentials must never be used in production.
- **Physical scope:** This is **not** an actual two-PC test. It does not prove Windows Firewall, router isolation, LAN discovery, physical network delays, certificate deployment across devices, or real-world disconnect patterns.

## Commands

From `D:\CoS-Test\madar-desk`:

```powershell
python -m unittest discover -s tests -p test_lan_v1_acceptance.py -v
py -3.12 -m unittest tests.test_lan_v1_acceptance -q
python -m unittest discover -s tests -p test_lan*.py -v
python -m unittest discover -s tests -p test_role_profiles.py -v
python -m unittest discover -s tests -p test_*.py
```

## Acceptance cases

| Area | Evidence from `test_lan_v1_acceptance.py` | Expected behavior |
| --- | --- | --- |
| Two instances | Two active HTTP(S) listeners, separate `Bridge` and account paths | Updates and tokens from host A cannot affect or authenticate on host B |
| Multi-user permissions | Admin, scoped editor, scoped viewer and an account on the other host | State filtered by project, viewer POST rejected, editor cannot create admin |
| Private data | State, profiles and user listing checks | Project scopes enforced, user-list forbidden outside admin, no password hashes returned |
| Endpoint schema | Bad typed logins, wrong password, bad JSON, wrong content type, unknown route, wrong verb | JSON failures with 400/403/404/405/415, not uncontrolled socket termination |
| Login throttling | Six bad login attempts then correct password | Same-IP login blocked temporarily; existing authenticated session still works |
| Simultaneous edits | Two concurrent writes with the same revision | Exactly one 200; the second 409, no silent overwrite |
| Role-change race | Editor write and manager role downgrade in parallel | No deadlock, viewer role effective on later writes |
| Offline conflict | Real listener shutdown, local pending edit, host edits same card, restart | Conflict raised; host update retained and local pending edit preserved |
| Offline reconciliation | Real listener shutdown; client edits card A while host edits card B | Both non-overlapping changes retained after reconnect |
| HTTPS pin | Correct hash and colon-delimited form, deliberately wrong hash | Correct pin authenticates; wrong pin fails before HTTP login and creates no server session |

## HTTP API contract relevant to LAN v1

The listener is limited to private/loopback client IPs and serves JSON with `Cache-Control: no-store`. It exposes explicit routes, **not** a static web or file server.

- `POST /api/login` accepts `{username, password}` and returns `{token, user}` (12-hour token session). Incorrect credentials return **403**. Non-string credentials return **400**. After six failures from one source IP, login attempts are blocked for approximately 120 seconds.
- `GET /api/state` with `Authorization: Bearer <token>` returns `{state, revision, user}`, filtered to the account's projects. `POST /api/state` accepts `{state, revision}` and returns a new `{state, revision, user}`. Server-side revision checks reject stale edits with **409**; viewers cannot write (**403**).
- `GET /api/users`, `POST /api/user`, `POST /api/users` (delete), `POST /api/reset-password` are administrator operations (**403** otherwise). `GET /api/profiles`, `POST /api/profile`, and `POST /api/password` require authentication; profile updates cannot change roles or project grants.
- Other explicit routes exist for collaboration, finance, scheduling and attachments. Their complete domain workflows are **outside this acceptance suite**; those modules require their own tests.
- Unknown paths return **404**, wrong GET/POST pairing on a valid route **405**, malformed JSON/invalid accepted shapes **400**, non-JSON POST content type **415**, and oversized body declaration **413**. Response error objects contain an `error` string. No static file contents or password hashes are returned by user-list responses.
- The legacy HTTP transport is **unencrypted** and should only be used on a trusted private network. HTTPS with full SHA-256 certificate fingerprint verification is the secure mode. A certificate fingerprint must be obtained from the trusted host channel, not merely read from a potentially hostile network message.

## Changes made within the assigned implementation file

1. Acquired the LAN account lock before the state lock in server-side `write_state` to match account-management ordering. The earlier state → account lock path, reached while preparing the write response, allowed potential deadlock against an administrator changing account grants.
2. Re-resolved authorization while holding the lock for state writes and account changes. This prevents a queued request from proceeding with a stale pre-downgrade role.
3. Applied consistent account locking to user lists, profile operations, password changes, account deletion, state reads, collaboration, finance, attachments and scheduler operations. This serializes a permission decision with an in-flight role change and prevents lock-order inversions.
4. Validated `/api/login` username and password types before dictionary lookup or hashing. Previously an array-valued username caused an unhandled `TypeError` and closed the HTTP connection without JSON response.

## Remaining limitations / release gates

- Two separate physical Windows PCs and their firewall/TLS configuration remain **untested**.
- No packet capture was performed. The wrong-fingerprint assertion verifies lack of an HTTP login/session on the test server; cryptographic implementation relies on Python's TLS library and its pinned-connection code.
- Stress, long-duration partition, transport packet loss, process crashes and database recovery under concurrent writes were **not** covered here.
- The client-side offline merge logic lives in `offline_exchange.py` and `native_app.py`; this suite exercises it but did not edit it.
- End-to-end Windows EXE GUI behavior and a full installer/release build are **not** covered here.
- Any separate findings concerning cross-account profile-cache handling in `native_app.py` require owner review and tests outside this file ownership.

The acceptance outcomes above apply to the exact isolated loopback test environment and are not a claim of production or physical-network certification.

## Observed regression results

- Focused v1 acceptance: **8/8 PASS** with `unittest discover`.
- All matching LAN tests (`test_lan*.py`): **27/27 PASS**.
- Role/profile tests: **8/8 PASS**.
- Direct module invocation with Python 3.12 (`py -3.12 -m unittest tests.test_lan_v1_acceptance -q`): **8/8 PASS**, approximately 28 seconds, after the import compatibility change.
- Full Python suite, on the same working tree before the qualified-import compatibility edit: **294/294 PASS**, approximately 126 seconds. The later compatibility edit changes only test fixture import resolution; the direct module run above covers that change.
- The unrelated Python ZIP tests emitted warnings about duplicate entries in disposable fixtures; the full suite nevertheless exited successfully.
