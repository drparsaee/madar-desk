# E0-E7 source QA: post-pilot triage (NOT ACCEPTED)

**Repository:** Madar isolated worktree HEAD `32bd8ffe5ebbb0f4cd5c011c59323ed32f8647ac`.
**Scope:** Python **source tests only**, each in separate temporary Windows
APPDATA/LOCALAPPDATA/TEMP/USERPROFILE/HOME. `test_packaged_madar_host_exe.py`
was **excluded** by runner policy. No installed EXE, real accounts or finance
document was opened. The worktree was dirty and had concurrent new-file work,
so this result is a run-specific observation, not a frozen release snapshot.

## Full run, including the new E1/E2/E3/E5/E6 pilots

```powershell
py -3.12 -B tools/modernization_python_suite.py --workers 5 --timeout 120 --report D:\CoS-Test\MTR_E0_E7_fullqa_20261109_continuation.json
```

Observed exit **1** and report:

| Signal | Value |
|---|---:|
| Discovered / excluded / executed modules | 234 / 1 / 233 |
| Passed / failed / timed-out modules | 202 / 31 / 0 |
| Reported test cases | 2,264 |
| Skipped / expected failures | 5 / 2 |
| Unexpected failures / errors | 21 / 124 |
| Elapsed | 161.8 seconds |

All new metadata-only test modules ran successfully in this full sweep,
including 29 E5 durable amendment tests, 28 E3 store, 34 E2 host store, 8
E2 TLS, 5 E1 TLS, 4 E6 TLS, 15 Radar host adapter, 22 CRM store, 20 E6
host notice adapter and 18 E6 notice store. The three *cross-repo signed
peer registry* cases were **skipped** in this generic run because its
per-process environment did not set `MTR_TARAZ_SOURCE`; separately, they
were directly run with explicit detached Taraz source and passed 3/3.

## Initial 31-module fail set and observed causes

The JSON report is the primary line-by-line evidence. Categories below
distinguish what the failure actually demonstrates, rather than labeling
all failures "old" or declaring that tests should simply be ignored.

| Category | Representative observed failures | Interpretation / allowed remedy |
|---|---|---|
| Explicitly retired finance API assumptions | `test_accounting_bridge`, `test_authenticated_intake_cas`, `test_finance_bridge`, `test_finance_overview`, `test_standalone_accounting_host`, `test_rial_host_security_invariants`, `test_purchase_host_adversarial` | Test code expects Madar's previous *standalone* financial mutation/ledger functions. Runtime now intentionally raises `PermissionError` (`حسابداری از مدار جدا شده است`) or route returns 404. Do **not** restore the posting API merely to turn tests green; identify the corresponding migrated Taraz acceptance coverage first |
| Legacy finance object/backup/export fixtures | `test_card_trash_contract`, `test_list_archive_contract`, `test_release_persistence`, `test_release_lan`, `test_sqlite_export_bridge`, `test_unified_bridge`, `test_user_acceptance_workflows` | They assert legacy finance presence in Madar state, migration or snapshot. May conceal unrelated persistence regressions, so they still need separate non-finance characterization, not blanket deletion |
| Obsolete Python/JS bridge import contracts | `test_provider_csv_bridge` and `test_integrated_update_theme_20261103` reported `ImportError: cannot import name 'ACCOUNTING_JS_BRIDGE' from native_app`; `test_js_bridge_surface` assumed retired finance methods remain exported | Old test dependency/bridge contract. Preserve runtime finance boundary and adapt targeted tests so operational updater and JS bridging still get real test coverage |
| 403-versus-404 on removed routes | `test_integration_http_security`, `test_lan`, `test_lan_v1_acceptance`, `test_lan_display_roles` | Removal returns 404, a valid negative denial. Adjust exact tests to assert **route absence even for admins** instead of resuscitating standalone financial endpoints |
| Presentation feature-map mismatch | `test_lan_display_roles`: seven server feature keys absent from client `src/interface_mode.js`, including `projectFinance` and `financeHub` | This is independently observed configuration drift. No blanket removal/addition until approved UI-vs-authority contract is reconciled; a 404 test adjustment alone does NOT fix it |
| Native titlebar/backup contract | `test_integrated_native_titlebar_ux_phase2`: 2 failures and 3 errors, including missing old `FakeFinancialBackup` instances, abnormal close and path guard expectation | Mixed older financial-close behavior and a potentially live path/close issue; needs targeted tests of current *non-finance* unsaved-state close safeguards |
| Transient HTTP fixture/runtime | `test_automation_buttons`: `ConnectionAbortedError [WinError 10053]` in the first sweep | Cannot conclude a regression or correctness from one aborted local connection; rerun under isolated test profile and examine if reproducible |

## Differential rerun after initial test-policy fixes

Changes to `tests/test_integration_http_security.py` and
`tests/test_js_bridge_surface.py` made their negative security expectations
consistent with intentionally retired finance API and JS bridge methods.

```powershell
py -3.12 -B tools/modernization_python_suite.py --workers 5 --timeout 120 --failed-only D:\CoS-Test\MTR_E0_E7_fullqa_20261109_continuation.json --report D:\CoS-Test\MTR_E0_E7_failed_only_20261109_postpolicy.json
```

Observed: **3/31 modules PASS, 28/31 FAIL**, 233 tests, 17 unexpected
assertion failures and 124 errors. The three passing modules were
`test_integration_http_security`, `test_js_bridge_surface` and
`test_automation_buttons`. The last had failed with a Windows socket abort
in the first run; it passed on rerun **without a source fix**.

After that rerun, test-only assertions in `tests/test_lan.py`,
`tests/test_lan_v1_acceptance.py` and a `test_lan_display_roles.py` route
assertion were also changed to require 404 for retired standalone finance;
these were **not included in the above 3/31 follow-up snapshot**. A separate
fresh run is needed to decide their later actual pass/fail status.

**Disposition:** SOURCE QA remains **BLOCKED** until migrated non-finance
behavior, official Taraz contract, stable restore/upgrade safeguards and
E7 installed acceptance independently pass. Neither this document nor the
test policy corrections close any of AC-01..32 or G-01..08.

### Later scoped rerun after the rest of the retired-route corrections

Additional test-only negative-contract changes to `tests/test_lan.py`,
`tests/test_lan_v1_acceptance.py`, and `tests/test_lan_display_roles.py`
now explicitly require the **retired accounting routes remain absent (404)**.
The role-map characterization was also changed to require exact parity of
active UI keys while asserting the **seven known legacy finance display IDs**
remain server-only for compatibility and are not exposed in the current
client. This is presentation compatibility, **not** financial authorization.

With the same **31 original failed modules** only (no claim about all modules):

```powershell
py -3.12 -B tools/modernization_python_suite.py --workers 4 --timeout 120 --failed-only D:\CoS-Test\MTR_E0_E7_fullqa_20261109_continuation.json --report D:\CoS-Test\MTR_E0_E7_failed_only_20261109_postretirement.json
```

**Observed exit 1:** 31 executed, **6 passed / 25 failed**, 233 reported
tests, **12 failures, 123 errors**, zero timed-out. Previously failing
`test_lan_display_roles`, `test_lan`, and `test_lan_v1_acceptance` now pass;
`test_js_bridge_surface`, `test_integration_http_security`, and
`test_automation_buttons` also pass. This is a **differential subset**;
it is not a fresh all-module QA pass, and the 25 remaining failed modules
cannot be declared harmless without more analysis.
