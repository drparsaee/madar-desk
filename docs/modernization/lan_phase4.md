# ExecPlan | LAN origin and Content-Length validation, phase 4

## Purpose / scope

Starting commit: `60beedd`, branch `modernization/phase2-20261101`, isolated Windows worktree. Harden the LAN HTTP request boundary without altering real profiles, finance ACLs, public API paths, passwords, certificates, native app data, or deployment. This worker owns `lan.py`, the new `tests/test_lan_security_framing_phase4.py` and this document only.

## Existing behavior and evidence (2026-11-01)

`LanService.start().Handler.process()` uses `urlparse(self.path).path` as the local route and converts POST/PATCH `Content-Length` using `int()`; `GET` validates digit syntax. HTTP allows only unsigned decimal digit sequences in Content-Length. Authorization derives from the bearer session and per-service ACL, and the HTTPS client pins the server certificate before submitting credentials.

Baseline isolated synthetic request tests at `60beedd`:

- `POST /api/login`, `Content-Length: +N`, legal JSON body: HTTP **200**, creating a session; test expected **400**.
- `GET http://untrusted.invalid/api/state` with a valid local bearer token: HTTP **200**, routing the absolute-form authority as if it were a local origin-path; test expected **400**.
- `PATCH /integrations/v1/cards`, `Content-Length: +2`: HTTP **404**, because no integration router was installed; the test is changed to an ordinary route to characterize the framing gate independently of optional integration setup.
- Normal POST login and GET `/api/state`: **200** and correct state.
- Missing `Host` in HTTP/1.1 login returned **200** and created a session; independently reproduced using a raw `HTTPConnection.putrequest(..., skip_host=True)` request.
- `GET //api/state` with a valid token returned **200**: Python's `BaseHTTPRequestHandler` normalized the leading `//` in `self.path` before route dispatch. A new failing characterization test proved that testing only `self.path` was insufficient; the final guard checks the original request target from `self.requestline`.

## Design / parity contract

1. Apply an ASCII unsigned-digit and length-bound check to `Content-Length` for *all* methods before any route dispatch, including login and optional integrations. Preserve the previous integration `413` response for negative (`-1`) or oversized declared lengths; leave method-specific byte limits and GET zero-body rule intact.
2. Require the local LAN HTTP API request-target to be an origin-form absolute path (`/api/...` or `/integrations/v1/...`) without a fragment or external authority. Read the original request line to avoid Python HTTP's `//` path normalization bypass. Existing `pinned_https_json` sends origin-form targets. Reject ambiguity before authentication or route dispatch. Do not reinterpret absolute URI authorities into a local route.
3. Require `Host` for HTTP/1.1 as specified by HTTP framing. Keep existing duplicate-header and `Transfer-Encoding` rejection; maintain JSON media-type enforcement, TLS certificate pinning and host-side authorization. HTTP/1.0 without `Host` retains its former compatibility.
4. Preserve normal login, private TLS and authenticated GET/POST, original JSON response framing, no writes when parsing fails, and 405 on unsupported valid-method routing.

## Progress / validation (2026-11-01)

- **CHARACTERIZED:** prior to edits, four behavior tests produced three HTTP mismatches: signed positive `Content-Length` on login returned 200 instead of 400; an external absolute-form target with matching local route returned 200 instead of 400; a missing HTTP/1.1 `Host` on login returned 200 instead of 400. Legitimate POST/GET parity stayed green.
- **INITIAL REGRESSION FOUND AND REPAIRED:** the first six-module adjacent run completed 43 cases with one failure: preexisting Integration test expected `413` for negative `Content-Length`, while the initial global syntax gate returned `400`. The gate was adjusted to retain `413` for negative/oversized body lengths while rejecting signed positive lengths.
- **FOCUSED VERIFIED:** `python -m unittest tests.test_lan_security_framing_phase4 tests.test_integration_http_security.MountedIntegrationSecurityTests.test_malformed_body_headers_and_url_have_controlled_failures -v` finished **6/6 PASS**, exit code 0, using fresh disposable `APPDATA` and `LOCALAPPDATA` and loopback-only synthetic server credentials.
- **ADJACENT RERUN:** the eleven-module LAN/TLS/integration/security suite ran **86** tests in **128.933 seconds**. **4 ERROR** in `tests.test_lan_finance_projection`, all at fixture `setUp` calling `LanService.upsert_user()` for non-existent `p-sample`; the other **82 completed without error/failure**. The suite exit code was **1**; it cannot be reported as green. A separate fresh-profile `native_app.Bridge().getState()` inspection returned `project_count=0` and `has_p_sample=False`, confirming the fixture requires a sample project that a clean profile does not contain. `upsert_user` and `Bridge` were not modified in this work. This explains the observed error, but no independent full-suite baseline was run against pristine HEAD.
- **FINAL VERIFIED AFTER RAW-TARGET FIX:** ten-module LAN/TLS/integration/security suite excluding the known failing `tests.test_lan_finance_projection` fixture ran **83/83 PASS** in **127.222 seconds**, exit code 0: `python -m unittest tests.test_lan_security_framing_phase4 tests.test_lan tests.test_lan_tls tests.test_lan_v1_acceptance tests.test_integration_http_security tests.test_task_accounting_lan_security tests.test_lan_auto_reconnect tests.test_lan_discovery tests.test_lan_display_roles tests.test_lan_user_creation_flow -q`. Includes the new `//api/state` raw-target regression test. All runs used disposable `APPDATA` and `LOCALAPPDATA` locations.
- **DIFF VERIFIED:** `git diff --check` returned exit code 0 after the LAN code edit; final diff check and syntax compile are part of worker handoff.

## Risks / limitations / release gate

Absolute-form request targets can be legal HTTP proxy-style syntax, but this direct LAN API is documented and used as an origin-form endpoint; rejecting absolute-form requests is a deliberate fail-closed application contract. Hostnames and `Host` headers are not treated as authentication. Two-machine network firewalls, real installations, proxies, operational data migrations, and complete full-project regression remain outside this change. At the time of the 86-test run the finance fixture lacked sample seeding; the prime agent subsequently **reported** repairing and passing that fixture in isolation, which this worker did not independently rerun. Commit, push and release belong to the prime agent and must be reported distinctly.
