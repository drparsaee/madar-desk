# E1 AI usage host adapter | isolated in-process pilot

Date: 2026-11-09. Baseline worktree HEAD `32bd8ff`. **Status: source-only implementation and synthetic tests.** No source/UI/router/worker-store modifications, commit, push, installed host or deployment.

## Scope and integration API

New standalone `madar_ai_usage_host_adapter.py` exports:

```python
adapter = MadarAiUsageHostAdapter(
    lan_service, ai_usage_store, org_id=host_owned_org_id,
    identity_key=host_owned_stable_secret_bytes,  # >= 32 bytes; not persisted here
    clock=host_utc_clock,                         # optional; UTC now by default
)
response = adapter.handle(lan_session_token, command_json_bytes_or_str)
```

JSON must have exactly `schemaVersion: 1`, `action`, `projectId` and `data`. Write actions additionally require strict `manualAction: true`. Bounded at 4096 UTF-8 bytes. Duplicate nested/top-level keys, NaN, malformed UTF-8, unknown fields and actions, unexpected nested objects, foreign actor/role/org IDs and inappropriate types fail closed. No raw prompt, API key, BYOK token or customer record field is accepted.

| Action | Access | Fields in `data` |
| --- | --- | --- |
| `grant_get` | Admin | `userId`, `provider` |
| `grant_set` | Admin and explicit action | `userId`, `provider`, `enabled`, `cloudEnabled`, `monthlyRequests`, `monthlyTokens`, `monthlyCostMicro`, `expectedVersion`, `eventId`, optional `expiresAtUtc` |
| `cloud_consent` | AI-enabled editor/admin and explicit action | `requestId`, `provider`, `payloadDigest`, `eventId` |
| `consent_revoke` | AI-enabled editor/admin and explicit action | `requestId`, `eventId` |
| `reserve` | AI-enabled editor/admin and explicit action | `requestId`, `provider`, `payloadDigest`, `estimatedTokens`, `maxCostMicro`, `eventId` |
| `usage_get` | AI-enabled editor/admin | `provider` |
| `reservation_get` | AI-enabled editor/admin | `requestId` |

Providers are only `local_ollama`, `openai`, `gemini` and `anthropic`. No provision exists to call a provider, use an API key, download a model, mark a request dispatched, complete paid usage, cancel/refund, send a prompt or change official Taraz/financial records. A reservation remains `reserved` and cannot initiate network work. There is **no external port or LAN HTTP route** in this module.

## Host trust boundary

Each command acquires `LanService.lock` and then `bridge._lock`, and obtains a fresh saved account through the actual `LanService.account_for(token)`. It confirms the requested project exists in the saved `bridge.getState()` project list and is inside current account project grants; deleted/expired sessions, viewer role and AI-off accounts cannot reserve. Admin policy management is allowed while the admin's own AI is off; target account must be a currently registered admin/editor in the same project. Accounts cannot gain role, actor, project or organization authority from the JSON body.

The constructor `org_id`, trusted clock, and a host-owned **stable secret HMAC key** are never supplied by client commands. Before writing to the existing `AiUsageStore`, the adapter maps organization, project, user, target user, request ID, event ID and submitted 64-hex payload digest to deterministic domain-separated HMAC pseudonyms. Neither raw LAN usernames/project identifiers nor the secret key are stored in its SQLite tables. Admin reads return pseudonyms, not plain usernames; the existing host UI may correlate with its own authenticated user directory. Key rotation/recovery needs explicit stable-key lifecycle design, backup and migration; loss of the key breaks lookup of prior pseudonymous records.

The store independently enforces bounded per-organization/project/user/provider grants, monthly UTC request/token/cost-micro budget caps, compare-and-swap, one-time cloud consent, expiry, grant version and immutable audit event IDs. New consent expiry is set by the **host UTC clock** to 5 minutes. For exact event replay, the adapter recovers the original immutable host timestamp from the store's `ai_audit` table, preventing a later host clock reading from producing an event-hash mismatch. The adapter is coupled to that v1 audit schema; future storage migrations must account for it.

**Important caveat:** This is a consent *intent*, not independently proven user gesture or safe prompt selection. The client currently submits an opaque 64-hex digest; this module cannot prove it corresponds to the selected text or that any text is non-sensitive. In production, the authenticated host must inspect and privacy-check the **exact user-selected text**, derive a host-keyed digest from that verified text and enforce origin/CSRF/TLS/gesture controls *before* accepting any future cloud-send permit. The current code does **not** expose a cloud send permit or transport method, so this gap does not grant network access.

## Synthetic verification

Isolated `TemporaryDirectory`, `AiUsageStore` SQLite file, real `LanService` class with test-only saved projects/users and synthetic sessions, one real synthetic-password `authenticate()` path, no `LanService.start()`:

```
py -3.12 -B -m unittest -q tests.test_madar_ai_usage_host_adapter tests.test_madar_ai_usage_store tests.test_madar_ai_provider_policy tests.test_madar_ai_draft
```

**Observed: 79 tests, OK**, including 24 new adapter and 55 neighboring AI store/policy/draft tests. Cases cover admin grant/get, real synthetic account authentication, AI-off and revoked viewer/project/session, event replay across adapter restart and host-clock changes, consent request/provider/digest binding and expiry, grant version invalidation, quota CAS/concurrency and UTC month boundary, 2 isolated organizations on one SQLite file, strict JSON injection rejection, no available dispatch actions, local flow with `socket.socket` patched to error, invalid host key/clock, and on-disk absence of raw synthetic user/project/org identifiers, digest and host key. Python compilation of both new files also passed.

This is not a real TLS deployment, app UI acceptance, connected model inference, real BYOK flow or installed multi-device test. Ledger-level checks do not guarantee real provider billing or hard token ceilings. The host must supply stable secret management, trustworthy UTC time and monotonicity safeguards, private file ACL, backup/recovery, authenticated consent gesture and prompt-content gate before any production cloud feature.

## No-commit boundary

Only the new adapter, its new tests, and this document are created. Existing `madar_ai_usage_store.py`, `lan.py`, `native_app.py`, `madar_ai_provider_policy.py` and shared UI code were not edited. No real profiles, network traffic, key persistence, cost, remote push or deployment.
