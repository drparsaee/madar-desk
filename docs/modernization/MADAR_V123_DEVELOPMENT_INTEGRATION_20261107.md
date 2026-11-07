# Madar development baseline: 1.0.23

Date: 2026-11-07. This note applies to the **Madar task manager** only.

## Verified source baseline

- Immutable release source: `22dbf1eac7652e4dac5026c1edc23092f1bd20ec` on `feat/madar-ux-execution-20261104`, package version `1.0.23`.
- Native Gantt/conversations integration: `feat/madar-v123-gantt-chat-20261107`, worktree `madar-v123-gantt-chat-20261107`, branched **from 22dbf1e**.
- Web PWA/API integration: `feat/madar-v123-web-integration-20261107`, worktree `madar-v123-web-integration-20261107`, branched **from 22dbf1e** and incorporating the independent PWA commit `d48c094`.
- Older worktrees `madar-desk` (package `1.0.13`) and `madar-web-pwa-20261106` (package `1.0.22`) contain uncommitted changes. They are **source inputs, not bases for new releases**. Do not reset, clean, overwrite, or release from them.

## Collision policy

1. Develop on the relevant new `1.0.23`-based integration branch. Do not edit the immutable release worktree to trial features.
2. `src/App.jsx`, `src/teamplus.jsx`, `src/features.jsx`, `lan.py`, `native_app.py`, and release metadata are shared conflict hotspots. Only one integrator should edit each of these at a time. Feature workers should use separate files or distinct branches and hand over an explicit diff.
3. Keep **Madar task data** separate from **Taraz accounting**. Taraz exchange is optional, manual, default-off and proposal-based. Never restore accounting UI or accounting endpoints from pre-1.0.23 branches by accepting an older merge conflict side.
4. The Web PWA and native Windows app stay independently buildable and independently installable. Do not share their live databases or credentials.
5. Do not package, install, deploy, push or claim a new release based only on compilation. Require regression tests, real UI acceptance and a separate release check; do not touch user task profiles or financial data for synthetic tests.

## Status at creation

- Native worktree: targeted 35 Python, 19 JS and 17 settings JS tests passed, native Vite production build passed. This is **development verification**, not an installed EXE acceptance.
- Web worktree: PWA baseline merged and WIP transferred, Web Vite production build passed, focused tests had 8 passed and 1 skipped; full Web suite was still running when this note was drafted.
- Original 1.0.23 release branch, installed application, user data, and pre-existing dirty worktrees were not modified by this integration.
