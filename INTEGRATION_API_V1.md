# Madar Desk 1.0 — External Integration Adapter (opt-in library)

## Status and security boundary

This module is an **implemented, versioned, bounded in-process HTTP router**, **not a running external API**. `integration_api_v1.py` creates **no server**, does not register endpoints in `lan.py`, and does not modify `native_app.py`. The existing LAN server must explicitly mount it after the Prime agent reviews and integrates it.

For v1, the adapter **fails closed** unless its `LanService` is actively listening with an `ssl.SSLSocket` and both TLS certificate/key configured. A plaintext LAN server returns JSON `503 https_required`. Do **not** mount it into an HTTP listener, reverse proxy it to HTTP, or skip the existing HTTPS fingerprint verification used by native clients. Obtain the pinned SHA-256 certificate hash from the administrator over a trusted channel. This code does not independently validate clients' TLS traffic; it relies on the host's existing TLS socket and the integrator mounting the router on that same server.

There is no public onboarding, no unauthenticated endpoint, no browser cookie authentication, no CORS policy or CSRF exception, no new open port, and no automatic outbound webhook/SSRF-capable delivery.

## Python integration contract for Prime

```python
from integration_api_v1 import IntegrationRouter, API_PREFIX

# Existing authenticated LanService, already started with a cert and key.
router = IntegrationRouter(lan_service)

# Trusted *in-process* admin workflow, not exposed as an HTTP route.
# admin_lan_token must already belong to a logged-in LAN administrator.
created = router.issue_key(admin_lan_token, "sample-editor",
                           permissions=("read", "write"),
                           lifetime_seconds=3600)
# created: {key, keyId, expiresAt, username, permissions}
# Show the random secret once to an explicitly authorized administrator.
# DO NOT log it, store it in plaintext, or send it over HTTP.

resp = router.handle(
    "GET", "/integrations/v1/cards?projectId=p-sample&limit=20",
    {"X-Madar-Integration-Key": created["key"]}, b""
)
# resp.status: int; resp.headers: dict[str, str]; resp.body: bytes (JSON)

# Revoke via trusted in-process management only.
router.revoke_key(admin_lan_token, created["keyId"])
```

When mounting this adapter in the existing `lan.py` request handler (owned by Prime, **not modified** in this task):

1. Keep the current LAN authentication and TLS listener unchanged. Instantiate **one** `IntegrationRouter` per running LAN service; reuse it for all requests. Do not expose `issue_key` or `revoke_key` as public HTTP actions.
2. Route **only** `/integrations/v1/...` to `router.handle`, and only from the **same HTTPS listener** (not a separate socket). HTTP must fail closed. Do not accidentally allow an HTTP port to inherit a router attached to an HTTPS service.
3. Read request bodies with an explicit upper limit of **8192 bytes before allocation**, reject negative/oversized `Content-Length`, and pass exact `bytes` to the router. Preserve full header names/values, reject duplicate security headers including `X-Madar-Integration-Key` and `Idempotency-Key`. A plain dict may lose duplicates before the router sees them.
4. Translate `IntegrationResponse.status`, `.headers` and `.body` to the HTTP response without altering JSON. Forward query strings unchanged. Never echo tokens in logs, exceptions or HTML.
5. Key issuance/revocation requires a trusted administrator workflow. The adapter is not automatically visible to external clients merely because it has been imported.

## Authentication and authorization

- Separate random **384-bit secret**: `mdv1_` + URL-safe token. Supplied only in the `X-Madar-Integration-Key` request header. LAN Bearer tokens are **not** accepted by the adapter.
- Only a currently authenticated `admin` LAN session can call the trusted local `issue_key` / `revoke_key` methods.
- Keys are bound to **one named existing LAN account** with explicit `read` and/or `write` capabilities. Maximum TTL 86,400 seconds; minimum 60 seconds; default 3,600 seconds.
- Raw secrets are returned once. The router keeps only SHA-256 key digests in RAM; maximum 512 active keys. They are **not persisted**, so every restart requires explicit re-issuance. `keyId` is not a secret.
- Every request checks account existence, live role, live project grants, capabilities, key expiry, and the account's password-hash revision. Password reset or account deletion invalidates the corresponding keys; a role downgrade immediately removes write privileges. A scope downgrade immediately hides removed projects.
- The integration adapter **cannot** create accounts, edit roles, access passwords, query finance, read attachment bodies or mutate arbitrary task/board fields. Even an admin-bound key sees only the defined safe projections.
- Successful `PATCH` requests use the same `LanService.write_state` authorization and optimistic revision checks as normal LAN clients. Requests run under the LAN account lock to prevent role-change authorization races.

## Versioned endpoints

All paths have prefix `/integrations/v1`. `GET` takes no body. JSON error responses contain `{"error": "stable_code", "version": 1}` and do not return internal exception messages.

| Method | Path | Capability | Response |
| --- | --- | --- | --- |
| GET | `/me` | read | `{version,user:{username,role}}` |
| GET | `/projects` | read | `{version,projects:[{id,name}]}` |
| GET | `/cards?projectId=ID&limit=N` | read | `{version,revision,cards,hasMore}` |
| GET | `/cards/ID` | read | `{version,revision,card}` |
| PATCH | `/cards/ID` | write + editor/admin | `{version,revision,card}` |

Card projection is an explicit allowlist: `id`, `projectId`, `title`, `status`, `priority`, `dueDate` (when those keys exist). All fields related to costs, project prices, finance, checklists and attachment paths are omitted. Project projection contains only `id` and `name`. Unknown or out-of-scope card IDs return the same `404 not_found`. Listing defaults to 100 cards and permits limits 1–200. There is **no paging cursor** in v1: `hasMore=true` means the caller requested a bounded subset, not that additional records are pageable through this endpoint.

`PATCH /cards/ID` requires:

```http
PATCH /integrations/v1/cards/card-id HTTP/1.1
X-Madar-Integration-Key: mdv1_<secret>
Content-Type: application/json
Idempotency-Key: exact-unique-job-identifier

{"title":"Updated title","revision":"<64-character-sha256-revision>"}
```

Only those two JSON properties are accepted. `title` must be nonblank, 1–160 characters after trim, and cannot contain control characters. `revision` must match the latest revision returned to that account. A stale revision returns 409 and never overwrites a newer save.

### Idempotency limits

- Required `Idempotency-Key`: 1–100 ASCII characters matching `[A-Za-z0-9][A-Za-z0-9_.:-]*`.
- A successful request is cached under **(integration key ID, idempotency key)** and its canonical method/path/JSON SHA-256 fingerprint.
- Exact retries return the original successful JSON result without another mutation. Reuse with different content/path returns `409 idempotency_key_conflict`.
- Authorization, account role, project visibility and expiration are rechecked **before** replaying the cached response.
- Cache is in-memory and bounded at 1,024 records, with expiry at the key expiry or after 1 hour, whichever is sooner. After process restart, keys are invalid; there is no durable idempotency journal. CAS remains the authoritative defense against blind overwrites.
- Two distinct keys attempting a simultaneous update using the same old revision can produce only one successful commit; the loser receives 409.

## Expected status codes

| HTTP status | Meaning |
| --- | --- |
| 200 | Allowed read or applied/idempotently replayed title change |
| 400 | Invalid path, input fields, JSON, query, key format or missing idempotency key |
| 401 | Missing, invalid, expired, revoked or password-invalidated integration key |
| 403 | Authenticated account lacks capability/role/permission |
| 404 | Unknown endpoint, card ID, or card outside current project scope |
| 405 | Unsupported method |
| 409 | Stale revision or conflicting reuse of idempotency key |
| 413 | Request body exceeds 8192-byte bound |
| 415 | JSON required for PATCH |
| 503 | Existing LAN service has no active TLS socket |
| 500 | Internal fault, generic error only |

No redirect handling and no public `OPTIONS`, `POST`, `PUT`, `DELETE` or `PATCH` endpoints outside the narrow card-title endpoint are part of v1.

## Tests

```powershell
python -m unittest discover -s tests -p test_integration_api_v1.py -v
py -3.12 -m unittest tests.test_integration_api_v1 -q
python -m unittest discover -s tests -p test_lan*.py -q
python -m unittest discover -s tests -p test_role_profiles.py -q
```

The dedicated suite uses a disposable real `native_app.Bridge` and a running TLS-capable `LanService`, but calls the in-process router directly. It validates admin issuance, separate key authentication, transport fail-closed, strict JSON, cross-account and project visibility, no financial output for *any* role, read/write separation, viewer restrictions, safe title updates, replay, stale revision, password reset, role/scope changes, key revocation/expiry, and cross-router key isolation. It does **not** claim that public REST endpoint wiring, remote API client interoperability, or a deployed HTTPS port have been tested.

Observed in this worktree:

- Direct Python 3.12 integration-adapter suite: **11/11 PASS** (33.73 s).
- Existing LAN/TLS and v1 LAN acceptance suite: **27/27 PASS** (51.71 s).
- Existing role/profile suite: **8/8 PASS** (14.62 s).
- Full Python or npm suites were **not rerun** by this worker; Prime owns the whole-application acceptance gate.

## Not implemented / follow-up

- **HTTP mounting in lan.py is NOT implemented** in this worker ownership. Prime must integrate and test it explicitly if external REST access is required.
- No durable integration key vault, key rotation workflow in UI, durable replay journal, per-key quotas, pagination tokens, webhook registration/delivery, event subscriptions, external SaaS credentials, finance/invoice REST, or bulk mutations. These are intentionally excluded from v1's safe bounded contract.
- Server protection remains dependent on correct LAN TLS configuration, trustworthy initial fingerprint distribution, administrative key issuance and protecting the host filesystem. No blanket claim of production security certification or two-device deployment testing is made.
