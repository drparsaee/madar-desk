# E1 Radar CRM host adapter | synthetic in-process pilot

Date: 2026-11-09. Worktree baseline: `32bd8ff`. **Status: implemented and verified at the named unit/integration-test scope**, not installed, mounted or deployed.

## Contract

`RadarHostAdapter(service, store: RadarCrmStore, *, org_id: str)` is constructed only by a trusted MadarHost bootstrap. Its sole entry point, `handle(token: str, command_json: bytes | str) -> dict`, accepts exactly one bounded JSON command and returns a detached JSON-compatible result. It has **no HTTP registration, socket listener, background scheduler or network transport**.

Every command has `schemaVersion=1`, `action`, `projectId` and `params`. Mutations additionally require `manualAction: true` (strict boolean). The upper bound is 8192 UTF-8 bytes; duplicate JSON keys, unknown command/parameter names, nested objects, unknown actions and JSON nonfinite constants are rejected. Supported actions:

| Mutations | Read-only |
| --- | --- |
| `create_contact`, `update_contact` | `get_contact`, `list_contacts` |
| `record_note`, `schedule_followup` | `list_history`, `list_due_reminders` |
| `complete_followup`, `soft_delete_contact` | |

Write parameters include a caller-stable event ID and `occurredAt`; updates require `expectedVersion` for SQLite CAS. The explicitly supplied timestamp is **user-reported, not host-authenticated**. A later host transport may provide a durable host-issued event timestamp or intent while preserving identical retry payloads. Read limits are enforced by the existing CRM store (maximum 100).

## Host authority and permissions

Inside `LanService.lock` and `bridge._lock`, the adapter calls **the existing authenticated** `service.account_for(token)` on every request, reads the host's currently saved project IDs from `bridge.getState()`, and validates LAN account `projects` grants. Organization comes **only from constructor `org_id`**, not client JSON. Actor, role, access grants and assignment candidates come **only from current** saved LAN user accounts. An absent, expired or deleted session fails closed.

Admin accounts may manage contacts, assign current editor/admin coworkers who hold the requested project grant, and soft-delete. Editors may create and update their owned contacts, record explicit interactions and schedule/complete their assigned follow-ups. Viewers have no mutation privileges and can only read CRM records visible under store ACL; the adapter does not offer viewer assignment. Per-contact ownership, reassignments, event idempotency, read scope and optimistic version enforcement remain independently checked by `RadarCrmStore`.

This pilot assumes a **single organization per LAN host registry**. Cross-organization access is partitioned by injected host `org_id` and composite SQLite keys. A future genuine multi-organization MadarHost needs an authenticated membership registry instead of inferring tenant membership from an organization-wide LAN user list.

No request carries official Taraz party identifiers, accounting/ledger objects, auto-generated messages or outbound delivery. Radar CRM does not call the independent E4 party matching pilot.

## Synthetic evidence

Executed in the isolated worktree, using `TemporaryDirectory`, test-only `LanService` (without `start()` and without port binding), test-only bridge project state, and separate synthetic SQLite:

- `py -3.12 -B -m unittest -q tests.test_radar_host_adapter tests.test_radar_crm_store tests.test_radar_party_match_preview` -> **48 tests passed**, 15 adapter, 22 underlying CRM store, 11 independent E4 party matcher; exit code 0.
- `py -3.12 -B -m py_compile radar_host_adapter.py tests/test_radar_host_adapter.py` -> exit code 0.

Adapter cases cover real password login to `account_for` in one test, test-only authenticated session fixtures for the other cases, explicit human actions, customer lifecycle, assigned internal reminders, duplicate keys/oversized/unknown JSON and actor/role/org injection attempts, expired/revoked LAN sessions, malformed saved grants, cross-project access, independent two-tenant organization partitions on a shared SQLite file, unchanged event replay/CAS conflicts, and two concurrent adapter calls. A test patches `socket.socket` to reject network access while the full in-process human flow runs.

## Integration boundaries

The production router, installed LAN TLS listener, certificate pinning, rate limiting, CSRF/origin handling, durable trusted event-time issuance, log redaction, real operating-system DB ACLs, backup/restore, multi-device behavior and separate authorization of installed host runtime were **not tested or changed**. The host must separately validate TLS before exposing this handler. `manualAction: true` is a per-request contract, not independent cryptographic proof of a human click. Keep browser/client capabilities outside the trusted constructor and session-principal derivation.

No existing source files were modified as part of this worker assignment. No network endpoint, real profile, real customer data, official Taraz operation, commit, push or deployment.
