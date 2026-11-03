# Accounting UX correction evidence — 2026-11-03

Source baseline: LocalForge `main` at `5f1c2a9225f6cdbf31b003ca7034b93c9ae2fd89`.
Changes were developed in the separate `fix/madar-accounting-ux-fixes-20261103` worktree.
No installed executable, real financial database, host, or canonical `main` was changed.

## Implemented within this branch

- **UX-01:** On light invoice-composer surfaces, label text remains dark and readable
  in both themes, including additional item-template controls. The light invoice-list
  description also receives a readable text color.
- **UX-02:** The horizontally scrolling cash-flow table has a labelled, keyboard-focusable
  region and a visible focus ring.
- **UX-03/04:** The first screen now exposes direct links to frequent tasks and a separate,
  prominently labelled snapshot of *unsettled issued* sales and purchases. Posted cash
  movements remain separate. The snapshot excludes drafts and historical imported
  balances, subtracts allocations and returns, and identifies overdue documents whose
  due dates are known. Invalid amounts or unsafe aggregates show an unknown amount
  with an explicit reconciliation warning.
- **UX-05:** On narrow screens, the invoice composer uses the existing Ribbon for the
  back action and hides duplicate breadcrumb/secondary back buttons. Save/add-line
  actions remain in a sticky toolbar. The amount summary remains visible.

## Synthetic verification

- Node/React-focused accounting suites: **51 passed / 0 failed**, including
  new outstanding, overdue, returned, draft-exclusion and overflow assertions.
- Vite production build: passed. Existing output-size warning remains.
- Chromium headless with read-only synthetic `RIAL` view:
  **9 axe-core 4.14.0 checkpoints**, **0 reported violations**. Each checkpoint
  retained 1–2 `incomplete` items for manual inspection.
- Dark-theme invoice labels: all **18 measured visible labels** in the two
  inspected composer screenshots (1440px and 390px) had measured contrast
  **≥ 8.38:1**. This is a measured subset, not a global WCAG compliance claim.
- At 390px the table region could receive keyboard focus and `ArrowLeft`
  moved horizontal scroll position from **0 to -40px** (scroll width 540px,
  viewport width 330px).
- **10 screenshots** from this branch at desktop and mobile widths in light and
  dark themes, the axe records,
  layout measurements and console checks are in
  `docs/modernization/evidence/accounting_ux_fixes_20261103/`.
  Browser execution reported **zero page errors and console errors**.

Reproduce after building the Vite site using
`node scripts/accounting_ux_fixes_browser_20261103.cjs` with `axe-core`
available under `.uiux-tools/node_modules/axe-core/axe.min.js`, or set
`ACCOUNTING_UX_AXE` to that file. Set `ACCOUNTING_UX_DIST` to use
an alternative build-output folder.

## Verification still required before release

The browser used a synthetic host API that disallows posting. No real financial
records were edited. WebView2/EXE, human keyboard and screen-reader testing,
high-volume data, native print flows, and actual ledger reconciliation remain
outside this branch's acceptance evidence. The unchanged financial-audit findings,
including FIN-01 and FIN-04, still govern any profitability claims.
