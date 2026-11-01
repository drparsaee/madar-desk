# ExecPlan | LAN request boundary, phase 3

## Purpose and boundary

Current SHA before this change: `7e0bcdffcc1f0938a2fee2140d1e60b78891bb89`, branch `modernization/phase2-20261101`. User priority: strengthen LAN security without changing authentication, finance ACL, persisted user data, certificates or deployed executable.

## Existing observed behavior

The shared HTTP handler in `lan.py` rejects duplicate header names and `Transfer-Encoding`, but ordinary `/api/` GET handlers accept a non-empty `Content-Length` without consuming it, unlike `/integrations/v1/`. POST currently uses `Content-Type.startswith("application/json")`, admitting the invalid type `application/jsonp`. The synthetic loopback HTTP characterization test `tests.test_lan.LanTests.test_http_rejects_get_bodies_and_masquerading_json_media_types` **failed on the unmodified handler**, observing HTTP 200 for `GET /api/me` with a two-byte JSON request body, versus expected 400.

## Plan

1. Keep existing guards and API route behavior.
2. Reject GETs declaring a nonzero Content-Length globally before authentication or routing; malformed Content-Length fails closed. Zero-length GET remains valid.
3. Parse the POST media-type token exactly, ignoring case and permitting normal `; charset=...` parameters. Reject non-JSON media types with existing 415 response.
4. Run the new characterization test, LAN/TLS/security adjacent tests with isolated `APPDATA`/`LOCALAPPDATA`, and `git diff --check`.

## Parity and release gates

- Existing legitimate GET/POST clients and HTTPS certificate pinning behave as before.
- Invalid media types and nonempty GET bodies are rejected without authentication, data writes or account state mutation. This is an intentional fail-closed change.
- No exposed HTTP API routes or financial schema changed.
- Test results and limitations recorded after execution. No claim of all-user LAN coverage or a production installer acceptance.

## Progress and independent baseline comparison (2026-11-01)

- **Baseline characterization: FAILED as expected.** Before modifying LAN code, an authenticated GET with `Content-Length: 2` returned HTTP **200**, violating the test's required HTTP 400.
- **Bounded fix:** ordinary API GET now rejects nonzero, malformed and unreasonably long declared bodies. Normal zero-length GET and legitimate JSON POST remain compatible; `application/jsonp` now returns 415.
- **Focused tests: 2/2 passed** using disposable LAN loopback profiles. `git diff --check` passed.
- **First adjacent suite:** 110 tests ran, 2 errors in `tests.test_lan_user_creation_flow`. To distinguish regression from inherited fixture mismatch, **unmodified main** commit `482b898` was separately run with the same four LAN user-creation tests and reproduced **exactly the same 2 errors**.
- **Root cause of inherited failures:** tests relied on project `p-sample` but a real first-run profile is intentionally empty. Added `native_app.initial_state()` strictly to the disposable fixture in `tests/test_lan_user_creation_flow.py`, identical in purpose to the existing explicit LAN sample setup. The four restored tests and new framing test passed **5/5**. No customer first-run seeding was introduced.
- **Final 11-module adjacent rerun:** `python -m unittest tests.test_lan tests.test_lan_tls tests.test_lan_discovery tests.test_lan_v1_acceptance tests.test_lan_user_creation_flow tests.test_task_accounting_lan_security tests.test_standalone_accounting_identity tests.test_standalone_accounting_backup tests.test_standalone_accounting_auto_backup tests.test_madar_update_contract tests.test_codex_upgrade_parity -q`, under fresh disposable `APPDATA` and `LOCALAPPDATA`, finished **110/110 passed, zero errors**, about 105 seconds. One offline-backup test deliberately prints `Backup refused: Backup destination already exists` to stderr while checking the no-overwrite contract; the test runner still finished `OK` with exit 0.

## Remaining acceptance limits

- This covers the named 11 Python modules, not all 168 Python test files or a two-machine TLS/LAN deployment.
- There is no real customer import, no Parsian database access, no new installer and no full accounting acceptance from this change.
- The user's installed version remains unchanged. Only a reviewed source branch may be delivered after Git verification.
