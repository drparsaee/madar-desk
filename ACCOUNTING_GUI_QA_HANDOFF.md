# Madar Desk accounting workspace native GUI QA handoff

**2026-10-21 | Status: harness updated, synthetic tests passed; NEW EXE interactive QA NOT RUN.**

This tranche changes only `gui_user_flow.py`,
`scripts/v1_gui_smoke.py`,
`tests/test_gui_smoke_harness.py`,
`tests/test_interactive_gui_harness.py`, and this new handoff document.
There are **no changes** to React, Python host/backend, finance, release,
APPDATA/LOCALAPPDATA of real users, Parsian/SQL, Drive or Git.

## Problem resolved

The **actual** app now renders `src/accounting_workspace.jsx` as a
**full-screen route**, not an accounting modal. Source evidence:

- `src/App.jsx:841–850`: `openAccounting` and conditional
  `<AccountingWorkspace … onExit={…}/>` replace `.app-shell`.
- `src/App.jsx:872`: admin navigation button says
  **«ورود به محیط حسابداری»**.
- `src/accounting_workspace.jsx:345–363`: root
  `.accw-root[dir=rtl]`, side navigation `.accw-side nav`, main
  `.accw-main`, exit `.accw-exit` **«بازگشت به تسک‌منیجر»**,
  a controlled selector `select[aria-label="واحد پولی حسابداری"]`
  with `TOMAN`/`RIAL`, and live explanatory currency disclosure.
- `src/accounting_workspace.jsx:6–11`: navigation tabs
  `overview`, `sales`, `purchases`, `manual`, `items`, `parties`,
  `accounts`, `payments`, `reports`, `migration`.

Old checks for `#madar-interface-mode`,
`.accounting-panel[role=dialog][aria-modal=true]`, or a
`[aria-label="بستن حسابداری"]` button are **obsolete**.
The harness now **rejects** those old diagnostics rather than treating
an old candidate as verified.

## Interactive sequence on a fresh owned Windows EXE

The native QA hook is **already in** `native_app.py:2098–2169`:
it runs `gui_user_flow.run_ui_flow(window,api)` only when
`MADAR_RELEASE_QA=1` and `MADAR_QA_INTERACTION=1`.
The smoke runner sets those flags only when `--interactive` is requested.
The script's `INTERACTIVE_REQUIRED` checks, all mandatory, are:

1. Verify RTL board and existing administrative accounting nav.
2. Read an **authoritative** pre-test finance snapshot via
   `Bridge._load_finance()` in the **isolated solo host only**.
3. Click the real accounting nav; verify `.accw-root`, side nav and main
   exist, the old board `.app-shell` is **not mounted** and accounting
   is not embedded in a dialog.
4. Verify selected overview tab; navigate to **دریافت و پرداخت**,
   verify its settlement form is rendered, navigate to **گزارش‌ها**,
   verify selected tab/header/pane.
5. Assert default `TOMAN` and the actual two options
   `TOMAN`/`RIAL`. Change using the native
   `HTMLSelectElement.prototype.value` setter + bubbling `change`
   so React receives the event. Require both selector and disclosure
   to reflect `RIAL`, while warning storage is in integer tomans.
   Switch to `TOMAN` and verify the display changed back.
6. Click the actual **بازگشت به تسک‌منیجر**; require
   `.accw-root` unmounted and normal Kanban `.app-shell` returned.
7. Re-read host finance state; it must equal the initial snapshot
   byte-for-byte at the Python value level. No sale, bank, payment,
   invoice or other finance submission is performed by the QA script.
8. **Only after every previous prerequisite passed**, use the existing
   create-task dialog inside the disposable project fixture, submit the
   unique QA task title and require exactly one real task persisted in
   `Bridge.getState()`. Confirm finance is **still unchanged**.
   On any prerequisite failure, stop before task creation and emit
   missing mandatory checks, so the release gate fails.

This confirms UI transitions/display, **not** correctness of every
financial arithmetic input or RIAL→TOMAN money conversion. The
`src/ir_money_display.js` conversion tests and ledger accounting tests
are separate acceptance gates. Merely selecting RIAL does **not**
alter the GL storage unit or post money.

The new Python `_require_isolated_qa` guard refuses to run unless:

- both explicit QA flags and `MADAR_QA_VIEW=sample-project` are present;
- the diagnostic root is an owned `.qa-v1-gui-isolated-*` scratch path;
- `APPDATA`, `LOCALAPPDATA`, WebView2 directory and host
  `Bridge.path` all point **inside that scratch**, not to a real
  user profile;
- bridge `connection.mode='solo'`, never real LAN/server/client.

## Process ownership and false-PASS prevention

`scripts/v1_gui_smoke.py` retains **WindowsOwnedJob** unchanged:
`CreateProcessW(CREATE_SUSPENDED)` → Job assignment with
`KILL_ON_JOB_CLOSE` → resume → Job-only termination on completion.
There is **no system-wide process search/kill or reuse of a running user's
application**. Each run creates its own isolated APPDATA/LOCALAPPDATA,
TEMP/TMP and WebView2 folders and removes that disposable tree afterward.
The runner rejects arbitrary EXEs outside the repo `release` root
and forbids writing output into real APPDATA or release.

Generic smoke remains available **without `--interactive`** and still
checks native bridge, font, board, card count, loopback localhost, etc.
Interactive checks have a strict required-key list: a stale EXE that
emits only old modal keys fails. For each check, `pass=true` alone is
insufficient; `observed=true` is required, except the persisted task
which must have integer `observed=1`. Missing `uiFlow`, denied
finance snapshot, unchanged-false, premature exit, report not written,
or absent selectors all fail, not silently pass.

## Validation actually performed

**Synthetic/host-free**, via Python standard library only:

```powershell
cd D:\CoS-Test\madar-desk
py -3.12 -m unittest discover -s tests -p test_gui_smoke_harness.py -v
py -3.12 -m unittest discover -s tests -p test_interactive_gui_harness.py -v
py -3.12 -m py_compile gui_user_flow.py scripts/v1_gui_smoke.py tests/test_gui_smoke_harness.py tests/test_interactive_gui_harness.py
```

Tests cover FakeJob lifecycle, one fresh synthetic report, obsolete modal
report rejection, reports lacking observations, finance safety flag failure,
fake WebView JS-script protocol and correct step ordering, early stop before
task creation, nonisolated profiles and connected hosts. The FakeWindow
returns synthetic scripted values; **it is not an actual WebView2**.
No native EXE was launched here. Running Python tests does not prove the
binary includes the latest `gui_user_flow.py` or the new React bundle.

## Prime-only: new uniquely named candidate after code freeze

Do not use older RC9/RC10/RC11 EXEs as proof. They can contain stale
React/QA hooks. **Prime must build a new unique candidate** containing
current `dist` and `gui_user_flow.py`, without overwriting prior
releases, and should verify PyInstaller's bundle includes the
QA module imported conditionally by `native_app.main()`. The existing
specs have `hiddenimports=[]`, so packaging of conditional imports
should be **verified**, not assumed.

From an authorized Prime-owned terminal, after source freeze:

```powershell
cd D:\CoS-Test\madar-desk
py -3.12 scripts/ensure_new_release.py Madar-Desk-v1.0-rc12-accounting-workspace-qa-20261021.exe
# Prime builds that exact *new* EXE in release/ after ensuring no name collision.
py -3.12 scripts/v1_gui_smoke.py --exe release/Madar-Desk-v1.0-rc12-accounting-workspace-qa-20261021.exe --interactive --timeout 150
```

The preflight fails if that release name already exists. A new unique name
must be chosen on collision. The `--interactive` command uses a temporary
QA-only Windows Job and deletes its scratch profile; **no separate QA
artifacts are retained** without an explicit safe `--output-dir`.
Add `--screenshot` only if a screenshot is needed; the native
screenshot is captured *after* the flow, usually back at the board/task
drawer, not inside the accounting workspace, so it **does not**
replace DOM-based accounting transition assertions.

### Release gate

**Green synthetic tests do not certify the new EXE.** The Prime's run must
return `status=PASS` and individually green
`interactive_accounting_workspace_fullscreen`,
`interactive_accounting_payments_visible`,
`interactive_accounting_reports_visible`,
`interactive_accounting_currency_rial_display`,
`interactive_accounting_currency_toman_restored`,
`interactive_accounting_workspace_closed`,
`interactive_finance_unchanged`,
`interactive_task_saved_to_host`, and
`interactive_finance_unchanged_after_task` alongside generic checks.
If the executable lacks the QA hook, refuses solo isolation, or contains
obsolete UI selectors, report **FAIL** and rebuild/fix through a separate
authorized source-owner tranche; do not weaken assertions.
