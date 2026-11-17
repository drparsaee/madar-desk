# E7: native titlebar regression realignment after accounting split

**Date:** 2026-11-09. **Worktree:** `D:\CoS-Test\000- Madar\madar-p2-gantt-notifications-20261107`, baseline `32bd8ffe5ebbb0f4cd5c011c59323ed32f8647ac`, shared dirty tree. **Owner-approved scope:** only `tests/test_integrated_native_titlebar_ux_phase2.py` and this new evidence document. No runtime source, host/peer finance, other tests or worker files changed; no commit, push, deploy, installer, real data or account operations.

## Current behavior established from source

- `native_app.py:3043-3057` replaces retired finance and accounting methods on `Bridge` with a `PermissionError` boundary; there is no `ACCOUNTING_JS_BRIDGE` in the task app.
- `native_app.py:3101-3115` only confirms or aborts a native close for `/` and `/index.html` when corresponding **task** JS callbacks are present. Unknown paths and `/accounting.html` return false.
- `native_app.py:3142` keeps `financial_backup=None`. For a solo host, `HostBackupScheduler` starts at `native_app.py:3145-3152` and stops on cleanup (`3521-3522`). These are task/host backup lifecycle operations; no standalone financial backup is configured by `main()`.
- `native_app.py:3157-3161` returns HTTP 404 for the retired `/accounting.html` page; `native_app.py:3177-3184` serves the task app on a loopback HTTP server.
- `native_app.py:3185-3233` reuses the existing `NativeAccountingCloseGate` **class** as a task close guard. Despite the historical name, it invokes task-only JS and preserves a veto/guard against incomplete saves. `standalone_accounting_desktop.py:65-104,107-245` handles bounded acknowledgement recovery if native `destroy()` is ignored or delayed.

## Before/after characterization

Under an isolated synthetic `APPDATA`, `LOCALAPPDATA`, `TEMP`, `TMP`, `HOME` and `USERPROFILE`, the untouched test module ran **five tests: three errors and two failures** (exit code 1). Three errors accessed `FakeFinancialBackup.instances[0]` when the deliberately retired financial backup was never initialized. The other two failures expected a financial backup failure prompt and an accounting-page abort callback, neither appropriate to the current task-only window.

Updated **only** `tests/test_integrated_native_titlebar_ux_phase2.py`:

- The synthetic window now starts at `/`, and its task callback simulation explicitly rejects retired and unknown paths. Actual production generated JS is still executed in the existing Node `vm` path matrix, so this is not solely asserting a mirror of the fake.
- Removed `FakeFinancialBackup`, obsolete financial editor JS expectations, and the fake `_standalone_accounting_store` entry from the test fixture. A rejecting `AutomaticStandaloneBackups` constructor mock (no return value) fails loudly if the app attempts to resurrect standalone backups.
- Preserved normal task close, dirty/pending-save veto, retry on later approval, host close lock state, WebView closing callback re-entry, exact document path filtering and missing-task-JS-hook denial.
- Replaced the obsolete financial backup failure case with a substantive **ignored `destroy()`** recovery test. A missing task abort acknowledgement leaves the host close lock engaged; after the task JS abort eventually acknowledges and a further user close action occurs, normal close completes. It exercises the real close gate/recovery functions with an `ImmediateThread` test scheduler, not a forced successful finance API return.
- Verify the synthetic `HostBackupScheduler` is started and stopped exactly once; this is an interaction test **not proof of actual task file backup bytes**. Added a check of current Bridge finance retirement and the absence of `ACCOUNTING_JS_BRIDGE`.
- Added an HTTP integration probe against the isolated ephemeral `127.0.0.1` task static server: `/` and `/index.html` return **200**; `/accounting.html`, `/%61ccounting.html` and `/nested/accounting.html` return **404**. No external network address or user profile was used.

## Observed validation

**Targeted command** (both before/after; Windows PowerShell wrapper temporarily sets all above profile variables to a unique disposable directory, enables `PYTHONDONTWRITEBYTECODE=1`, and restores those variables and removes only that disposable directory in `finally`):

```powershell
py -3.12 -B -m unittest discover -s tests -p test_integrated_native_titlebar_ux_phase2.py -v
```

After the changes, observed **7 tests, 7 passed, 0 failures/errors, exit 0**. Exact cases:

1. `test_ignored_destroy_requires_task_abort_ack_before_retry`
2. `test_integrated_loopback_does_not_serve_accounting_document`
3. `test_integrated_scripts_allow_only_task_document_paths`
4. `test_integrated_task_page_closes_with_host_task_backup_scheduler`
5. `test_integrated_task_page_pending_save_vetos_native_x`
6. `test_integrated_titlebar_vetoes_dirty_task_then_closes`
7. `test_retired_finance_bridge_methods_stay_inaccessible`

An intermediate revised run had one **test harness** error because `HTTPConnection` is not a context manager. It was corrected with `contextlib.closing` before the final successful rerun; no production code was changed to accommodate tests.

**Adjacent existing close-gate regression command**, using the same isolated
environment wrapper:

```powershell
py -3.12 -B -m unittest discover -s tests -p test_madar_native_close_ux_phase2.py -v
```

Observed **14 tests, 14 passed, 0 failures/errors, exit 0**. This separate
suite covers the reusable native-close primitive, including older independent
accounting scenarios, but passing it does not mean embedded accounting was
reactivated in `native_app.main()`. **Combined focused evidence: 21 of 21
tests passed** across the two commands, with no broad full-suite rerun.

## Boundaries and residual risks

`FakePeriodicBackup` verifies the host scheduler lifecycle, not the real snapshot content, durability or an installed EXE. The native JS is run in Node and pywebview calls are stubbed; genuine WebView2 event scheduling, keyboard accessibility and window lifecycle on the installed application still require acceptance elsewhere. The shared `NativeAccountingCloseGate` emits a historically named *accounting editor remains locked* diagnostic when a task abort cannot be acknowledged; the test verifies safe denial and recovery and does **not** claim that message is correctly phrased for nonfinance users. No live financial operation or real backup was performed. Other retired-finance tests remain under separate E7 ownership and were not edited.
