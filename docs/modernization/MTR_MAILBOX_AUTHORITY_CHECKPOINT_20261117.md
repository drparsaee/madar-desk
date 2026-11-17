# ECOSYSTEM PRIME | Mailbox authorization checkpoint | 2026-11-17

Status: `SOURCE_SECURITY_SLICE_PASS`; installed release remains `NO-GO`.

## Changes (isolated scope)

- `integration_company_grant_v1.py`: added `resolve_active(company_id, installation_id)` with read-only lookup of exactly one approved, unrevoked, unexpired Taraz pairing; validates account password revision, installation, read scope and workspace, without returning credentials.
- `integration_mailbox_authorizer_v1.py` (new): fail-closed `IntegrationMailbox` callback. Uses **trusted host-supplied current LAN admin session** for enqueue/reconcile/result-ACK; **trusted router-authenticated peer key** for poll/reply/delivery-ACK; checks actor lineage and current role, company grant, key revocation, workspace, operation and permitted read scope.
- `tests/test_integration_mailbox_authorizer_20261117.py` (new): synthetic Windows HTTPS/LAN + protected registry + signed durable-mailbox round-trip and negative cases.

## Observed verification

Command (repo: `D:\CoS-Test\000- Madar\madar-p2-gantt-notifications-20261107`):

```powershell
py -3.12 -B -m unittest tests.test_integration_company_grant_20261116 tests.test_integration_mailbox_authorizer_20261117 tests.test_integration_mailbox_v1_20261116 -q
```

Result: `Ran 25 tests in 10.527s` / `OK` / exit code `0`.

`git diff --check` exit code `0` (line-ending warnings only).

## Scope / limitations

- The existing `integration_mailbox_v1.py` and its tests were NOT edited; a previous worker owns them.
- Existing 19 dirty tracked Madar files and unrelated untracked files preserved.
- No commit, push, installer, production financial mutation, or installed EXE E2E here.
- The authorizer is **not yet mounted on the live Madar HTTP Router**, and Taraz has no completed mailbox poll/reply transport in this slice.
- For production wiring, instantiate authorizer only in trusted Python HTTPS host; implement `host_token` and `peer_key` callbacks from authenticated, **server-owned request context**, never from the browser or peer JSON. Revalidate grants on every operation.
- Parent directory and SQLite journal ACL must still pass independent security gate. Windows DPAPI migration/recovery and installed versions still need full acceptance.
- Prior Prime agent run status could not be queried from this conversation (`AGENTS_NO_CHAT`); no new workers spawned and no existing worker files overwritten.

## Next gate

Wire native admin enqueue/reconcile and authenticated peer poll/reply/ACK into existing HTTPS Router (no parallel listener), using this callback. Then E2E on disposable Clone: Madar -> queued read -> Taraz directory -> signed reply -> Madar result/ACK -> restart/revoke/lost-ACK tests. Do NOT claim `GO` until cross-app installed acceptance, backup/restore and version-compatible release gates pass.
