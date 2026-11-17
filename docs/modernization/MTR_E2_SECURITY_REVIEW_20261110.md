# E2 signed peer and MadarHost concurrency review (2026-11-10)

**Scope:** isolated Madar + detached Taraz source and synthetic tests. No official Taraz financial receipt, posting, source-of-truth identity validation, two-PC acceptance, deployment or network changes.

## Verified remediations in these isolated worktrees

1. **Cross-actor query binding, Taraz (worker-11 code and synthetic reproducer):** in `taraz_mtr_peer_registry.py`, a signed query must now match the original stored `actor_role` for that same request; a different correctly signed same-organization role is denied and its query row rolled back. New `tests/test_taraz_mtr_peer_registry.py::test_signed_query_requires_original_actor_role_without_delegation` failed against the old behavior (3 failed assertions) and passed after the patch. Taraz registry focused run: **12/12 PASS, exit 0**; this result was also freshly rerun by the prime in the detached worktree. Only the original actor role is supported, not a delegation feature. A currently authenticated signed peer query is still required.
2. **Shared-host lock isolation, Madar (prime patch and direct test):** `mtr_e2_host_peer_pilot.py` now authenticates the current principal, verifies immutable host snapshot, durably reserves the one-shot send slot and signs under `LanService.lock` + `bridge._lock`, then releases those locks before blocking `PeerLoopbackHttpsPilot.intake_once`. Likewise, `query_first` signs after host/gate checks under lock but performs the signed remote query without holding the common host/card locks. `tests/test_mtr_e2_host_peer_pilot.py::test_blocking_peer_transport_does_not_hold_shared_host_or_card_locks` ran against both callbacks and a separate thread acquired both shared locks during those callbacks: **1/1 PASS, exit 0**. Only the synthetic coordinator is modified; the live LAN route does not mount it.

## Post-patch regression actually executed

From isolated Madar with `MTR_TARAZ_SOURCE` temporarily bound to the detached Taraz worktree:

```powershell
$env:MTR_TARAZ_SOURCE='D:\CoS-Test\000- Taraz\taraz-mtr-e2-isolated-20261109'
$env:PYTHONIOENCODING='utf-8'
py -3.12 -B -m unittest -q tests.test_mtr_e2_host_peer_pilot tests.test_mtr_e2_dispatch_gate tests.test_mtr_lan_finance_adapter tests.test_mtr_peer_https_pilot tests.test_mtr_e4_local_catalog_pilot tests.test_mtr_e4_link_correction_pilot tests.test_mtr_acceptance_matrix
$code=$LASTEXITCODE
Remove-Item Env:MTR_TARAZ_SOURCE
exit $code
```

**70/70 PASS, exit 0 (59.822s)** after both security changes. Includes prior inherited cross-source methods, seven E4 local catalog checks, 12 new synthetic E4 impact tests and four matrix-structure checks. Counts are overlapping with earlier 46/47, 25 and 436 runs; do not add them as independent outcomes. Taraz registry tests additionally ran separately **12/12 PASS**. No installed host or official financial endpoint was exercised.

## Open security and operational risks

| Priority | Boundary | Evidence and safe next step |
|---|---|---|
| SCOPED FIX / OPEN E7 | Same-actor re-login and removed-card query-first | Subsequent same-day implementation added `HostRequestStore.recovery_snapshot`, `OneShotDispatchGate.recovery_status`, and current-session `MtrLanFinanceAdapter._recovery_principal`, used only by coordinator's read-only signed query-first. Three new synthetic TLS integration tests passed; 119/119 combined tests passed. Original send/store/gate APIs remain session-bound. No cross-actor role delegation, independently authenticated production Taraz, signed host journal or two-PC acceptance. See `MTR_E2_RELOGIN_AUTHORIZED_RECOVERY_20261110.md`. |
| MEDIUM | Total signed peer-query journal exhaustion | Taraz registry uses a lifetime cap of 10,000 query rows; additional queries eventually deny permanently. Need audited, replay-safe retention/capacity/rotation design. No deletion/TTL patch was made. |
| MEDIUM | Taraz test HTTPS admission | TLS handshake runs before the concurrent request semaphore; a stalled same-host unauthenticated connection may block accept. Bound handshake before/within admission with negative slow-client tests. No live TLS server changed. |
| MEDIUM | Durable signed-query evidence at Madar | Verified peer reply is currently returned to caller but not persisted as a separate signed *metadata* recovery observation. Existing official-receipt store must NOT be used to promote this synthetic peer lookup into a finance receipt. |
| OPEN | E1 UI scope and cloud consent origin | Worker-14 found three **observed UI gaps**: wrong-scope pseudo-ID responses are displayed/acknowledged; syntactically valid but forged preverified intent can record user intent. Current host has no model dispatch. Before UI mount, bind authenticated response scopes and host-selected content to explicit user action and reject forged hints. |

Separate E7 AC-05, AC-07, AC-12/13, AC-18/19 and G-03/G-06/G-08 all remain **OPEN**. Neither metadata arrival nor signed test registry response is an official Taraz receipt, approval, ledger entry or legally verified party link.

## Evidence provenance and limitations

The worker-11 read-only review identified the recovery, query-cap, TLS admission and unsigned journal risks; it reproduced the cross-actor bug in synthetic SQLite and later patched only the Taraz peer registry/test. The prime independently inspected the Madar coordinator and changed its shared-host lock scope, ran the new per-peer lock test and post-patch 70-test regression, and reran the Taraz registry's 12 tests. The review is **not** a remote penetration test, a full source audit or a production acceptance certificate. Both worktrees have other agents' uncommitted changes; no commit, push, deploy, installer, data migration or finance posting occurred.
