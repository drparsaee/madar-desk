# E2 signed query-first after same-actor re-login (2026-11-10)

**Status: source-only synthetic recovery SCOPED PASS. Not production/financial acceptance.** This later phase follows the narrower, previously blocked `MTR_E2_RELOGIN_RECOVERY_PILOT_20261110.md` worker report: the original store/gate APIs genuinely could not recover across sessions. The subsequent implementation adds **new distinct read-only APIs**, without loosening any original send/retry path.

## Explicitly added source contracts

- `mtr_lan_finance_adapter.py: MtrLanFinanceAdapter._recovery_principal(token)` obtains a **current** principal from actual `LanService.account_for(token)`, saved project registry and current user grant/finance-edit permissions while caller holds the host/card locks. Its permission set contains **only `mtr.read`**, never `mtr.prepare` or `mtr.manual_send`. No browser role/project claim accepted.
- `mtr_host_request_store.py: HostRequestStore.recovery_snapshot(...)` checks the current authenticated principal, **original owner user**, original organization/project and current visibility; insists on the original saved revision and previously MANUAL_SEND_AUTHORIZED state. It reads the original payload/hash/send key and original session only as trusted internal evidence. Existing `request_snapshot` and all write methods still require exact **original session**.
- `mtr_e2_dispatch_gate.py: OneShotDispatchGate.recovery_status(...)` checks the immutable original gate row and audit chain, comparing stored org, project, original actor **and original historical session**, SHA, revision and stable send key against the authorized outbox snapshot. It never grants or rearms a first-send slot.
- `mtr_e2_host_peer_pilot.py: MtrE2HostPeerPilot.query_first(...)` uses these read-only methods, validates the caller's task ID against the original saved immutable payload, then issues one signed **peer lookup**, not an intake/send. Neither card presence nor mutable card title is an authority source for recovery. Host/card locks are released before the peer HTTPS request.

## Fresh direct evidence

Three integrated pinned-loopback-HTTPS tests were added in `tests/test_mtr_e2_host_peer_pilot.py` and run directly (all **3/3 PASS, exit 0**):

1. `test_same_actor_relogin_signed_query_only_without_rearming_dispatch`: original session-bound outbox/gate read **both deny** new session; a current same-actor recovery read/query succeeds, status is only metadata `received`, and a new send under the new session is denied; exactly one test registry arrival.
2. `test_relogin_recovery_requires_current_actor_role_project_and_request`: different owner, mismatched task ID, revoked finance permission and revoked project grant all deny.
3. `test_deleted_saved_card_does_not_destroy_same_actor_query_first`: deleted current saved card does not erase query-first ability for the original owner and original project; a second send remains denied.

Post-change combined command in isolated Madar with explicit detached synthetic Taraz source:

```powershell
$env:MTR_TARAZ_SOURCE='D:\CoS-Test\000- Taraz\taraz-mtr-e2-isolated-20261109'
$env:PYTHONIOENCODING='utf-8'
py -3.12 -B -m unittest -q tests.test_mtr_e2_host_peer_pilot tests.test_mtr_e2_dispatch_gate tests.test_mtr_host_request_store tests.test_mtr_lan_finance_adapter tests.test_mtr_peer_https_pilot tests.test_mtr_e2_recovery_policy_pilot tests.test_mtr_e4_local_catalog_pilot tests.test_mtr_e4_link_correction_pilot tests.test_mtr_acceptance_matrix
$code=$LASTEXITCODE
Remove-Item Env:MTR_TARAZ_SOURCE
exit $code
```

**119 tests, OK, exit code 0 (69.200s)**, covering the newly added recovery paths and existing gate/outbox security. Counts overlap with prior 46, 70 and 436 runs. No new official financial evidence is generated.

## Remaining fail-closed limits

- Re-login by the **same actor with the same currently permitted finance role** is exercised. Changing the actor's role after original signing may cause peer signature actor-role rejection; no role-delegation signing or persistent original role upgrade protocol exists. Reject rather than impersonate.
- If the original project is no longer in the current trusted project registry or original actor's grants, recovery is denied. Restoration from removed/renamed project requires separately authorized archival recovery policy, not silent escalation.
- Original outbox and dispatch gate are **separate SQLite files**; there is no distributed transaction with peer registry or Taraz ledger. Query result is not durably stored as independently signed host recovery evidence.
- No real Taraz identity, official financial receipt, ledger post, physical two-PC LAN, Windows service, installed client, trusted real credentials, server restart/power-loss recovery, rollback or deployed secure route was validated. The coordinator is still `synthetic_only=True` and remains **not mounted**.
- E7 AC-12/13 and G-03 remain OPEN despite this new scoped recovery evidence.
