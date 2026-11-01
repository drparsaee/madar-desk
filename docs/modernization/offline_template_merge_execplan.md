# ExecPlan | Offline LAN structure reconciliation: templates and retries

## Purpose / scope
Owner directs continued automated checks/fixes after synthetic LAN acceptance, leaving physical-device testing to users. Prevent silent loss of offline board templates or unauthorized editor changes. Repository: D:\CoS-Test\madar-desk, initial main SHA 0c3855d73f0b3280c99e28f78f7f1d95b0690399. Scope: offline_exchange.py, tests/test_offline_exchange.py, tests/test_lan_v1_acceptance.py, this plan. No real profiles, database migrations, credential changes, deployed binaries or financial posting.

## Existing behavior / architecture
Bridge._sync_client_from_host uses OfflineStore.reconcile with allow_structure True only for a trusted host-authenticated admin. OfflineStore.reconcile uses three_way_merge; its task list and project list use identity-aware _three_way_items. For admin, stages, settings, workspaces and boards use scalar structural conflict checks. However, 'templates' are omitted from the editor-prohibited keys and from admin structural reconciliation, while LanService.write_state explicitly treats 'templates' as an admin-only structural field. As a result, pending template edits may be dropped silently after an apparently successful sync. Tests/test_offline_exchange.py currently exercises offline task changes, collision, and wrong-user protection.

## Plan / parity and acceptance
1. Characterize baseline in synthetic APPDATA, LOCALAPPDATA and TEMP: offline_exchange, bridge_offline, lan_auto_reconnect and local_state_cas.
2. Write failing tests: admin template edit survives nonoverlapping host task edit; concurrent template edits fail closed and preserve pending data; editor template edit fails; an already-applied admin settings edit is idempotent when latest equals local.
3. Update three_way_merge to cover templates as structural data under the same admin and editor policies used by LAN. Preserve existing task/project merge behavior and never merge concurrent different structure.
4. Run targeted and adjacent synthetic LAN/SQLite regressions; inspect diff. Commit and private LocalForge push only after checks, without changing installed Madar.

## Progress / validation
Baseline before modification: 24/24 passed from four relevant test modules, using disposable paths.
Red regression reproduced: four newly added tests in `tests.test_offline_exchange` yielded 3 failures and 1 error before modification. They demonstrated loss of the offline template edit, unauthorized editor template changes being silently discarded, lack of concurrent-template conflict, and an already-applied settings change being rejected as a conflict.

Fixed regression: four modules (`tests.test_offline_exchange`, `tests.test_bridge_offline`, `tests.test_lan_auto_reconnect`, `tests.test_local_state_cas`) passed **28/28** with disposable Windows APPDATA/LOCALAPPDATA/TEMP. The adjacent LAN/TLS/auto reconnect suite passed **24/24**. The SQLite/unified bridge/local CAS suite passed **49/49** in its own disposable profile. These are separate overlapping suites, not a claim of 101 distinct test cases.
The additional real HTTP/HTTPS acceptance case `test_admin_offline_template_survives_https_host_task_change` passed **1/1**: a synthetic administrative desktop Bridge saved a template offline during TLS host shutdown, host task edits were committed separately, and restart reconciled both into the authoritative host. This uses in-process host/service plus loopback and does not prove physical-PC behavior.
Following that addition, the entire `tests.test_lan_v1_acceptance` module ran **10/10**. Upgrade/restore parity modules (`tests.test_release_persistence`, `tests.test_release_restore_guard`, `tests.test_madar_update_contract`, `tests.test_codex_upgrade_parity`) passed **20/20**. Card/finance authorization bridge (`tests.test_finance_bridge`, `tests.test_finance_reference_guard`, `tests.test_task_accounting_lan_security`) passed **13/13**. All used separate disposable profile directories; validation of installed builds and customer-ledger migration is outside scope.

## Limits
The test proves bounded code and synthetic synchronization behavior, not production two-PC, GUI or WAN/Drive coordination. Admin structural keys are treated as whole values; concurrent modifications to different template entries may still require explicit user conflict resolution. No conversion between rial and toman.
