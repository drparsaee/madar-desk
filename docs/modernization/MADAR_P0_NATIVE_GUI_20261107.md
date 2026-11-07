# Madar P0: Windows GUI and planning-date save gate

Date: 2026-11-07. Base release: `1.0.23` at `22dbf1e`.

## Actual Windows WebView2 source QA

The harness `scripts/qa_p0_v123_webview2.py` launched `native_app.main()`
through **the installed WebView2 runtime** while redirecting APPDATA,
LOCALAPPDATA and WEBVIEW2_USER_DATA_FOLDER into a fixed, previously absent
synthetic worktree directory. A fake sample project and task cards were
created solely in this test profile. The real user profile and installed EXE
were not opened or changed.

Result: child exit 0, 24 of 24 checks true, 0 uncaught browser errors. Tested
real RTL rendering, sample board/card opening, Gantt mount with day/week/month
scale options, closing back to Kanban, project-chat modal, card comment
controls, settings UI, separate Taraz tab, disabled subscription checkout,
theme light/dark selections with distinct foreground/background, and label
manager. The Gantt DOM contained 4 synthetic rows and 42 axis cells.

Local synthetic evidence: `.qa-p0-v123-webview2/native-ui-acceptance.json`.
The QA root is deliberately retained rather than silently removed or
overwritten; the harness refuses reruns into an occupied QA root.

This is functional real WebView2 DOM/interaction evidence, not pixel-perfect
visual QA, a second physical Windows device, an installed EXE launch, or a
test of live accounting.

## Save integrity issue discovered and fixed

The two date fields in the card editor updated `plannedStart` and
`plannedEnd` independently. Previously, changing the start beyond the
existing end could reach autosave, while the backend rejects that range.
The source now uses `validPlanningPatch` at both the event boundary and
inside the latest React-state updater. Invalid ranges or non-string fields
are rejected before mutation, while a valid two-date edit and unrelated
task edits are allowed.

Regression cases are in `tests/gantt_model.test.cjs`, exercised in both
native and web integrations. Source builds, full tests, package signatures,
isolated 1.0.24 upgrade and rollback must be reported separately.
