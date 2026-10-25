# RC9 | Madar Desk Controlled User-Test Candidate

**Status:** candidate for controlled testing with synthetic/non-sensitive data only. **NOT production/stable or 100% Trello parity.**

## Artifact and release identity

- Exact EXE: `release/Madar-Desk-v1.0-rc9-user-testing-candidate.exe`
- Version in package.json/package-lock.json: `1.0.0-rc.9`.
- Windows EXE size: **13,865,133 bytes**.
- SHA256: `9D70EAC7D9F8D8E0BD313EFFC7C8BA3659F59A76843BCF467D57414940E4BBC1`.
- `npm run dist:rc` exit 0. Release guard checked the unique path and did not overwrite earlier RCs.

## Automated release QA evidence

- `py -3.12 scripts/release_qa.py --full` exit 0 before RC9 packaging:
  - Release regressions **19/19 PASS**
  - Python **684/684 PASS**
  - JavaScript **276/276 PASS**
  - **979 test executions passed**, including new accounting UI regressions and host-safety coverage.
- Additional focused financial-source Bridge test was created during the full QA run and **2/2 PASS separately**; do not count it in the 684 full-suite figure without a later complete rerun.
- `py -3.12 -m unittest tests.test_finance_reference_guard tests.test_user_acceptance_workflows tests.test_interactive_gui_harness -q` 18/18 PASS in disposable fixtures.
- `node --test tests/accounting_panel_ui.test.cjs` 11/11 PASS, plus existing panel tests in worker combined run 19/19 PASS. No real financial posting in the GUI was claimed.
- `npm run build` and PyInstaller one-file build exit 0 (log `.qa-rc9-user-build.log`).

## Actual EXE interactive checks

Command:
`py -3.12 scripts/v1_gui_smoke.py --exe release/Madar-Desk-v1.0-rc9-user-testing-candidate.exe --interactive --screenshot --timeout 120 --output-dir .qa-rc9-interactive`

- Exit **0**, **23/23 checks PASS** (8 base DOM/Bridge/board checks, 14 interactive steps, 1 screenshot integrity).
- Real WebView2 interactions: RTL and basic mode, switch to Finance, accounting navigation appears, dialog opens with accessible attributes then closes, task-creation form opens, typed Persian title, submitted creation, editor drawer appears, **Bridge.getState confirms exactly one newly persisted synthetic task**.
- Isolated APPDATA/LOCALAPPDATA/Temp/WebView2 profile created and removed by owned-job harness. No real accounts or user data touched.
- PNG integrity verified: **1484×921 px**, 142,610 bytes. Native screenshot callback `done:false` remains a known diagnostic mismatch despite complete valid PNG.
- Evidence: `.qa-rc9-interactive.log`, `.qa-rc9-interactive/v1-gui-smoke-jwdj7q_j/{diagnostics.json,screenshot.png}`.

## Defects corrected in this beta cycle

1. Financial source guard in `finance_reference_guard.py` invoked before host saves: blocks physical removal/migration of tasks linked to invoices/GL or cost overrides; soft trash and normal edits remain possible.
2. Project removal UI refuses nonempty projects to avoid silent cross-project reassignment of task/invoice references.
3. Long list-mode rendering now shares bounded progressive pages with board mode; React focus targets actual buttons and list wrappers, reducing worst-case DOM load.
4. Accounting panel refuses estimated/guessed purchase sources, requires authoritative positive cost, clear counterparty, explicit settlement invoice and amount, valid posting date, bounded TOMAN numeric input, and prevents stale project/asynchronous double submission.
5. Dialog keyboard focus trapping/return and accounting modal RTL/mobile/status feedback improved.
6. Beta version clearly appears in app footer; UI snapshot warning recommends no real user data.

## Still unverified or outside this candidate

- Full interactive accounting **draft→review→issue→settlement in Windows GUI**: Python Bridge integration passed, but GUI only opened/closed accounting modal automatically.
- Physical **two-Windows-client** LAN disconnection/reconnect/conflict and network hardening under real conditions.
- Real **1k/5k card FPS**, full keyboard/DnD accessibility and 5-user usability acceptance.
- Backup recovery covering **binary attachments, LAN credentials/accounts, planner settings and external Drive**. SQLite snapshot alone is not a complete system backup.
- New M08 alternate `accounting_gl.py` is not the authoritative unified posting engine. M10 proposal review is pure and not an automatic host AI writer. No dual posting or autonomous financial mutation.
- Legality of printed invoices, tax rules and external payment evidence has not been assessed.

Use `BETA_TESTER_GUIDE_FA_2026-10-21.md` and `USER_TEST_ACCEPTANCE_SCENARIOS.md` for controlled testing. No live deployment, migration or real-user data changes authorized or performed.
