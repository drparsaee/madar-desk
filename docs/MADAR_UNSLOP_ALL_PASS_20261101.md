# Madar Desk | Unslop across application surfaces | 2026-11-01

## Owner requirements

1. Top and side tab bars reveal **expanding labels**, with visible text and keyboard operation.
2. Start Madar on a **real task board** when the active workspace contains one.
3. Apply the [Unslop](https://github.com/heydamir/unslop) approach to the task manager's screen families, not just the Overview preview.
4. Use one **Vitrea graphite / blue** light-and-dark identity for the independent accounting workspace and its operational pages, while preserving all ledger data, arithmetic and permissions.

## Source boundary and provenance

- Isolated working tree: `D:\CoS-Test\madar-unslop-all-20261101` on `design/unslop-all-20261101`, based on previously tested `3dea053187e8a609bd08cb32b9868360593eca64`.
- Existing project-local skill: `.agents/skills/unslop/SKILL.md`, attributed to Damir Sokolovsky (CC BY 4.0), unchanged.
- Code changes deliberately limited to CSS, React **presentation/navigation state**, and tests. No accounting domain, persistence, migration, TLS, ACL, or installed EXE files changed.
- The full installed app still requires the existing offline Windows update and data-preservation acceptance gates. Git push is not a user installation.

## Applied design improvements

| Area | Before | After | Implementation |
| --- | --- | --- | --- |
| Top bar | Each label always visible in a tightly packed capsule | Inactive desktop items are compact icons; the active, hovered or keyboard-focused item expands to show its label. Mobile retains accessible text and horizontally scrollable actions. | `App.jsx`, `vitrea_navigation.css` |
| Side quickdock | Repeated icon-only round actions | On desktop, rail expands from 61px to 174px on hover or focus, revealing Persian labels; icon names remain available to assistive technology while collapsed. Mobile dock stays compact. | `App.jsx`, `vitrea_navigation.css` |
| Startup screen | Aggregate Overview initially | First existing valid board in active workspace is selected **in memory only** after loading. Empty workspaces keep their honest setup path; Overview remains one click away. No stored task is altered. | `App.jsx` |
| Task manager | Mixed decorative controls, tiny descriptions, hover lifting | Shared readable typography, neutral card chrome, consistent spacing, calmer hover, blue focus indicators, and meaningful stage/status colors preserved across board, list, task edit, dialogs, settings, search, planner and reporting. | `unslop_general.css`, `main.jsx` |
| Accounting | Main overview already Vitrea, many other tabs retained teal/off-white legacy surfaces | Shared graphite/blue light-dark tokens for all standalone tabs, invoice ribbon, forms, management KPIs, reports, tables, and the legacy embedded financial workspace. Genuine green/red financial statuses remain meaningful. | `accounting_unslop.css` imported by both accounting workspaces |

These are shared design-system passes, **not** claims that every nested dialog on every device was individually hand-reviewed. Source-specific rules may still need further visual tuning.

## Verified observations / unresolved gates

- Build from isolated worktree: `npm run build` successful; Vite's existing >500 kB chunk-size advisory still appears.
- Original focused browser test checked startup on a synthetic valid board, top and side label expansion, keyboard-accessible actions, RTL and accounting root background in dark/light: **passed** after correcting a light-theme specificity mismatch.
- Earlier complete Node regression following initial navigation changes: 529 passed, 0 failed, 0 skipped (sequential). Before a targeted correction, search had a double keyboard-focus outline and one test failed (528/529); after adding a narrowly scoped SearchPlus exception, the focused browser tests and full regression passed.
- New accounting synthetic read-only traversal checks all **17 standalone pages in both dark and light modes**, plus page width and JavaScript errors. The first fixture omitted required `companyProfile.history` and was corrected; the latest separate traversal passed for all 34 navigations. This is not a ledger accuracy or production migration test.
- **Final aggregate Node regression including new accounting and startup tests:** `node --test --test-concurrency=1 tests/*.test.cjs` executed under disposable `APPDATA`/`LOCALAPPDATA` after the final shared CSS changes. **530 passed, 0 failed, 0 skipped**, runner-reported duration `127333.53ms`.
- Visual QA: **38 synthetic screenshots** captured from Vite preview, including initial board, expanded quickdock, both accounting overviews and 17 accounting tabs in both themes. Local gallery: `analysis/unslop-all-shots/index.html`. The images are deliberately not committed to Git.
- Related native Windows Python tests: `python -m unittest tests.test_native tests.test_native_tls tests.test_madar_update_contract -q`, **32 passed, 0 failed**, using disposable profile directories; `python -m py_compile native_app.py` also passed. These are selected tests, **not** the full Python regression.
- Windows full Python suite, real Parsian migration and signed installer acceptance: **not part of this design pass**, therefore product release readiness remains **unverified**.

## Synthetic screenshot evidence

With `MADAR_UNSLOP_SHOTS` pointing to a local QA directory, the new tests capture initial board/expanded navigation and all 17 accounting tabs in both themes. Screenshots contain only synthetic fixture data; they are **not** financial customer records. Generated images and test logs stay local outside Git.

## Safety statement

- No production `APPDATA` or user database was opened for editing.
- No financial command API was provided to the accounting tab-rendering browser test.
- The account roles, debit/credit arithmetic, rial/toman distinction, document issuance and rollback processes are **not** altered by this code change.
- Keep the existing offline update preflight, verified backup, rollback and installer gates before distributing the modified UI.
