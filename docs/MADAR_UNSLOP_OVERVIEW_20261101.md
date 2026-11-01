# Madar Desk | Unslop UI pilot | 2026-11-01

## Scope and provenance

The user requested installation of [Unslop](https://github.com/heydamir/unslop) and an actual improvement to Madar. This is a **limited UI pilot**, not a new production installer or a complete redesign of accounting.

- Third-party skill source: `heydamir/unslop`, commit `a6f121eee5f29c2f74976b75456feae8b66afb3a`. Installed as `.agents/skills/unslop/` (14 original skill files with SHA256 equal to source, plus the original repository `LICENSE` text with trailing blank lines normalized for the Git whitespace check). Licensed CC BY 4.0. Credit: **Damir Sokolovsky**, [original repository](https://github.com/heydamir/unslop). Maintain this credit in copies/adaptations.
- Worktree: `D:\CoS-Test\madar-unslop-20261101`, branch `design/unslop-madar-20261101`, from existing private LocalForge `main` commit `fbe86e6c9c74c0988a8652e734888221ed6c43e5`.
- Target: `src/vitrea_overview.jsx` and `src/vitrea_overview.css`. No production profile, installed EXE, accounting ledger, networking, backups or private finance data were changed.
- The profile's existing global `~/.agents/skills/unslop` directory was different and preserved without overwrite; this project uses its complete, isolated copy.

## Audit before changes

Observed in **synthetic** Chromium preview and source:

1. The project overview gave six unrelated background colors to cards according to *array position*, not project status or user-selected project color (`tone-0` ... `tone-5`).
2. Panel subtitles, task subtitles and month labels were 10px on desktop; the last shrank to **8px** on 390px mobile. These measurements came from actual browser `getComputedStyle`, not estimates.
3. Three metric cards repeated illuminated icon circles next to their counts, diluting the hierarchy of the numbers.
4. Project cards, small badges and chart tracks used gradients, glossy surfaces and extra shadows competing with real task progress.
5. Existing strengths were retained: owner-selected Vitrea graphite/glass shell, Estedad typography, RTL, blue activity chart, stage colors with real semantic meaning, actual task/project aggregates, linked project/task actions.

## Direction (Unslop)

1. **Product:** a Persian Windows desktop workspace for projects, tasks and separate accounting.
2. **Character:** exact, organized, quiet.
3. **World:** practical task boards, document folders, graphite workspace surfaces.
4. **Moment:** one blue monthly-activity chart showing actual created tasks; stage colors remain meaningful categories rather than decoration.
5. **Signature:** a restrained blue completion bar on each project, using the existing computed task count.

No logo, brand palette, major navigation or financial behavior was redesigned. This is *polish mode*, not a new brand direction.

## Implementation by Unslop pass

- **Spacing:** repeatable 8/12/16px gaps, aligned panel headings and reduced pill-like padding; mobile three-metric row instead of a tall one-column stack.
- **Color:** replace six index-derived project tile hues with a graphite/light neutral surface; retain blue as the primary activity/progress accent and legitimate stage-category colors.
- **Icons:** remove redundant icons from metric cards, retain meaningful folder/action glyphs.
- **Copy:** preserve factual Persian labels, dates and counts; no invented KPIs or promotional copy.
- **Type:** raise desktop panel/task/month labels from 10px to 12px, mobile month labels from 8px to 11px, normalize strong emphasis.
- **Layout:** keep the owner-approved Vitrea dashboard sections, RTL, chart, stage list and clickable projects. Maintain 1440px desktop and 390px mobile without body overflow.
- **Details:** quieter border/shadows, smaller radius on project/task controls, consistent progress-track thickness and keyboard focus outlines.
- **Visuals:** no generated/stock illustrations, because these are real operational dashboards.
- **Motion:** retain short progress transitions with `prefers-reduced-motion` respected; remove ornamental hover lift from project tiles.

## Observed verification

1. Baseline `npm run build`: success after building the isolated worktree. Initial browser test required the `dist/` build; the first preview attempt before the build failed with an HTTP error, which was corrected by building and rerunning the same test.
2. Baseline synthetic Chromium overview metrics: `heading=10px`, `task=10px`, `month=10px`, `kpi=11px`, mobile `month=8px`, no horizontal body overflow.
3. After UI changes, `npm run build`: success (1704 modules transformed); output has the existing Rollup >500kB chunk warning.
4. After changes, synthetic Chromium overview: desktop dark/light `heading=12px`, `task=12px`, `month=12px`, `kpi=12px`; mobile `month=11px` and `kpi=11px`; 6 project cards and 9 task action buttons remain; `bodyScrollWidth` exactly 1440px at 1440px and 390px at 390px; no reported page JavaScript exceptions.
5. Focused Node test: `node --test tests/vitrea_overview.test.cjs tests/vitrea_runtime_ui.test.cjs` **4 passed, 0 failed**, including synthetic browser navigation to independent accounting and light/dark/mobile screenshots.
6. Full Node regression first executed in parallel: **525 passed / 3 failed / 0 skipped**. The three failures were Playwright timeouts in unrelated full-App runtime tests, with no proven source regression. This red result was preserved, not misrepresented as green.
7. The same full suite rerun with an isolated `APPDATA` and `LOCALAPPDATA` using `node --test --test-concurrency=1 tests/*.test.cjs`: **528 passed / 0 failed / 0 skipped**, runner-reported duration `113824.5899ms`. Sequential execution prevents competing local Chromium previews from exhausting their 10-second navigation limits.
8. Related Python desktop tests executed using disposable `APPDATA`/`LOCALAPPDATA`: `python -m unittest tests.test_native tests.test_native_tls tests.test_madar_update_contract -q`, **32 passed / 0 failed**. `python -m py_compile native_app.py` also passed. The full Python suite was not rerun in this UI-only pilot.

The local synthetic before/after screenshots (not customer data and not a deployed artifact) are under `analysis/unslop/before-overview/` and `analysis/unslop/after-overview/`. View them side by side with the local-only `analysis/unslop/compare.html`. A second series comes from the browser test with the optional `MADAR_QA_SCREENSHOT_DIR` variable. No screenshot of a real financial record was used.

## Release boundary

This pass touches React/CSS and tests only. It is **not** evidence of an upgraded installed EXE, complete accounting reconciliation, safe Parsian import, or acceptance on all Windows devices. The private branch must be reviewed/tested and merged or released through the existing documented update gates; do not overwrite live 1.0.2 or user `APPDATA` just to show the new design.
