# Madar Desk v0.5 RC1 — executable QA on Windows (2026-10-20)

**Scope:** The latest Windows binary that existed when QA started, plus a new
source-level full regression run. This is a **tested release candidate**, not
acceptance of the entire product or its live network/cloud behavior.

## Binary identity

- File: `D:\CoS-Test\madar-desk\release\Madar-Desk-v0.5-rc1.exe`
- Observed size: **13,503,659 bytes**
- Observed SHA-256:
  `E22F4FD9B3C9F2CC1D143F642490575CBD8ED2DFA513C8A19732C1E425803C0F`
- The test profile was kept inside this project, separate from the user's
  normal AppData, at `.qa-live-rc1-latest` and `.qa-rc1-live-ui`.

## Results and supporting logs

| Test | Result | Evidence |
| --- | --- | --- |
| `py -3 scripts\release_qa.py --full` | **Environment failure**: Python 3.13 lacks `webview`, two release modules failed import. This does not exercise the packaged EXE. | `.qa-live-20261020-full.log`, exit 1 |
| `py -3.12 scripts\release_qa.py --full` | **PASS**; 9 release regression tests, 240 Python tests, 17 JavaScript tests; process exit 0 | `.qa-live-20261020-py312-full.log` |
| Launch exact binary on Windows with isolated `APPDATA`/`LOCALAPPDATA` | **PASS** for initial UI startup | `.qa-live-rc1-latest/smoke.json`, `.qa-live-rc1-latest/screen.png` |
| WebView UI diagnostic | `readyState=complete`; `bridgeType=object`; `pywebviewType=object`; `fontLoaded=true`; `stageCount=5`; React root length 30799 | New exact-binary smoke report |
| Native Windows UI Automation: create task | **PASS**; `QA-RC1-Persist-20261020-2201` shown in UI and present in isolated `tasks.json` | QA window and `.qa-rc1-live-ui/AppData/MadarDesk/tasks.json` |
| Native UI Automation: edit task and checklist | **PASS**; title changed to `QA-RC1-Persist-20261020-2201-Edited`, step `QA-CHECKLIST-STEP` saved | UI Automation and isolated `tasks.json` |
| Close binary and launch again with same isolated profile | **PASS**; edited card visible again and checklist still present; task JSON SHA-256 unchanged by relaunch | `.qa-rc1-live-ui/smoke-restart.json`, file hash/UI inspection |

The screenshot PNG exists and was visually inspected: RTL layout, navigation,
Kanban cards and five columns render. The screenshot diagnostic's
`screenshot.done=false` was **not** reported as screenshot callback success.

## Observed issue

Opening the freshly created task's detail pane initially showed
`خواندن نظرات: Card not found` and `Card not found` in the comments and
attachment areas, while the task itself and its checklist persisted. After
restarting the same EXE and opening that task, neither error was present.
**Status: observed transient UI error, root cause unverified**. A likely
candidate is a timing issue around new task persistence, but that hypothesis
was not independently reproduced or proven. Add a regression for immediately
opening a new task before claiming these features reliable.

A subsequent automated project-creation attempt failed at UI Automation
control selection and is **inconclusive**. It does not establish an app defect
or a passing project-creation workflow.

## Not tested in this run

Two physical Windows machines, real Google Drive sync/outage/reconnect,
end-to-end attachment upload/download from a second PC, financial issuance
in the UI, a complete recovery including profile accounts and blobs, clean
Windows installation, comprehensive light/dark visual review, and official
invoice behavior. The program's integrated tests cover some underlying logic
but do not substitute for these acceptance scenarios.

**Decision: RC1 passes the isolated startup, task create/edit/persistence and
source-level automated regression checks. Full 0.5 release acceptance is
still open, with one transient UI error observed.**
