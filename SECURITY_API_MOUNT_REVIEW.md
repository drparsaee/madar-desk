# Madar Desk 1.0 RC — Mounted Integration API Security Review

## Exact scope

**Audit target:** the REST mount in the current `lan.py` handler for `/integrations/v1/*`, the existing `IntegrationRouter`, and the host-local admin-issued integration keys. This is an **end-to-end socket-level** test, not a simulated/router-only call.

**Owned deliverables:** new `tests/test_integration_http_security.py` and this review document. The worker did **not** change `lan.py`, `native_app.py`, `App.jsx`, or previous adapter/test files. Prime owns changes to shared code.

**Environment:** disposable `tempfile.TemporaryDirectory`; `APPDATA` set to an isolated test directory; `native_app.datadir` patched only during construction of each independent test `Bridge`. `LanService` listens at **127.0.0.1 on an OS-selected ephemeral port**. TLS uses the existing public test-only certificate/key in `tests/test_lan_tls.py` (never deploy those credentials). The client checks the exact leaf-certificate SHA-256 fingerprint **before sending HTTP headers**. A separate unencrypted LAN host runs for one isolation test.

**Not tested:** two physical machines, production certificates, Windows Firewall, network proxies/load balancers, public internet, packet-loss/reordering, persistence after abrupt process crash, or credential management in a real installed Windows EXE. In particular, this audit is not a security certification.

## How to execute

```powershell
cd D:\CoS-Test\madar-desk
py -3.12 -m unittest tests.test_integration_http_security -v
py -3.12 -m unittest tests.test_integration_http_security tests.test_release_integration_http tests.test_integration_api_v1 -q
```

Each test constructs a fresh HTTPS host and destroys its temporary files after listener shutdown. Request framing is tested with low-level `http.client.HTTPSConnection.putrequest/putheader/endheaders` so duplicate headers can be sent without a Python dictionary silently merging them.

**Verified results after Prime's framing fix:**

- `py -3.12 -m unittest tests.test_integration_http_security -v`: **11/11 PASS** (26.915 seconds).
- `py -3.12 -m unittest tests.test_integration_http_security tests.test_release_integration_http tests.test_integration_api_v1 -q`: **24/24 PASS** (64.545 seconds).
- An isolated test of the chunked-body regression **failed** before Prime's fix (200 instead of 400), then **passed** after it. The complete Python/npm suites were not rerun by this worker.

## Security cases and observed behavior

| Area | Scenario | Acceptance expectation |
| --- | --- | --- |
| Duplicate HTTP headers | Duplicate exact/mixed-case integration credential, `Content-Length`, `Content-Type`, or `Idempotency-Key` | HTTP 400; no mutation |
| Plaintext isolation | A different plain-HTTP LAN host receives `/integrations/v1/cards` | HTTP 404; router not mounted |
| Auth separation | Integration key offered as LAN Bearer token, LAN token offered as integration key | HTTP 403 and 401, respectively |
| Management route | Public attempts to create/list keys through integration REST | 405 for unsupported POST; 404 for missing GET route |
| Project isolation | Scoped editor, disjoint editor and zero-scope viewer list/read private cards | Only permitted projects/cards shown; hidden and missing card IDs both 404 |
| Financial projection | Test host stores nonzero project price and card cost; admin, editor and viewer query REST | Response only includes `{id,name}` for projects and explicit card-field allowlist; no financial data |
| Finance route isolation | Adapter requests for finance, invoice, user list and attachments | HTTP 404, regardless of key account role |
| PATCH replay | Same JSON and `Idempotency-Key` repeated | Identical successful response, no second mutation |
| PATCH conflict | Same idempotency key with different content; different key with stale revision | HTTP 409; first successful value retained |
| Permission changes | Editor downgraded to viewer after successful PATCH; then moved to different project scope | Old replay denied 403; removed card not disclosed (404) |
| Key revocation by account lifecycle | Viewer tries write; account password reset then deleted | Viewer 403; old keys 401 after password reset or deletion |
| Concurrent clients | Two different integration keys PATCH same card over real parallel HTTPS sockets with the same state revision | Exactly one 200, one 409 |
| Malformed input | Duplicate JSON properties, malformed JSON, NaN, arrays, arbitrary role field, control chars, bad revision, bad content type | Controlled 400/415; no state mutation |
| Bounded bodies | Oversized actual body, negative/oversized/nondecimal `Content-Length`, body attached to GET | Controlled 400/413; no update |
| URI validation | Encoded path separator, repeated query parameter | HTTP 400 |
| Certificate pinning | Correct TLS handshake with manually verified SHA-256; wrong pin through `pinned_https_json` | Wrong pin raises verification error before the key is sent |
| Transfer-Encoding | `GET /integrations/v1/cards` with `Transfer-Encoding: chunked`, a real chunked body and **no Content-Length** | HTTP 400 |

### Confirmed mount defect and resolution

**Finding MOUNT-SEC-01 — unsupported Transfer-Encoding accepted (fixed by Prime):**

Initially, the HTTPS mount read `Content-Length` with default `0` but did not check `Transfer-Encoding`. An authenticated request such as:

```http
GET /integrations/v1/cards HTTP/1.1
Host: 127.0.0.1
X-Madar-Integration-Key: <valid test key>
Transfer-Encoding: chunked

0

```

received **HTTP 200 with card JSON** instead of rejecting an unsupported body-framing format. The test deliberately sends **no** `Content-Length`. A first iteration of the fixture inadvertently supplied that header and incorrectly passed; the fixture was corrected before reporting the finding. The failing isolated regression then produced **200 != 400**, confirming the original issue. This demonstrated an HTTP framing ambiguity, **not** a proven exploitable request-smuggling chain.

The worker reported the finding to Prime. Prime patched the shared `lan.py` route to reject `Transfer-Encoding` whenever present (before body reading). Inspection of the mounted handler after that change confirmed the guard, and the **same raw-socket regression subsequently returned 400 and passed**. This worker did not edit shared files.

### Review observations

- The mount rejects duplicate HTTP header **names case-insensitively** before collapsing them to `dict(self.headers.items())`. This is necessary because a dictionary would discard ambiguity otherwise.
- Request bodies are length-bounded before `rfile.read` (8,192 bytes), and method/content restrictions are also enforced inside the router.
- A hashed integration key by itself is **not** a LAN Bearer token. The existing LAN endpoints do not become accessible by possession of an integration key.
- Adapter outputs remain a narrow data projection even for a key assigned to the administrator. An administrator's generic LAN credentials, however, have broader authorized access through their **separate** LAN endpoints.
- Dynamic role/project checks prevent cached successful PATCH replay after permission downgrade. Password reset/deletion invalidates the corresponding integration keys.
- The API's `Idempotency-Key` cache and issued keys are **in-memory**. RC cannot claim durable replay or credential persistence across restart; these are explicitly out of scope for v1.
- The integration key is carried in a request header and should never be copied to HTTP access logs, crash dumps or monitoring telemetry. No public API for key issuance exists.
- The client-side certificate pin must be provisioned through a trusted channel; the certificate from an untrusted connection alone is not an identity guarantee.

## Remaining RC release conditions

This suite is one security gate, not the entire RC validation. Prime should retain the new test in CI, continue enforcing HTTPS-only mounting and the `Transfer-Encoding` rejection, and run the full application tests and installer build separately. If a reverse proxy is added later, repeat request-framing and authentication tests through that proxy. Physical two-machine LAN acceptance is still outstanding.
