# Madar Desk 0.5 RC1: current evidence and unfinished acceptance

**As of 2026-10-20.** This is an evidence checkpoint, not production approval.
The current source tree is `D:\CoS-Test\madar-desk`, which is **not a Git
repository**. Preserve prior releases and use disposable user profiles for QA.

## What exists and has been observed

- A newer Windows executable exists at
  `release/Madar-Desk-v0.5-rc1.exe` (13,503,659 bytes; modified
  2026-10-20 21:37:37 local time). SHA-256 measured from the newer file:
  `E22F4FD9B3C9F2CC1D143F642490575CBD8ED2DFA513C8A19732C1E425803C0F`.
- `.qa-v05-rc1-final-build.log` ends with PyInstaller reporting **Build complete**.
- `.qa-rc1-final-tests.log` records **240 Python tests passing** and
  **17 JavaScript tests passing**, and the automated release QA reports PASS.
  This is evidence from the recorded test run, not an independent new run.
- `.qa-rc1-desktop/smoke.json` records `readyState=complete`,
  `bridgeType=object`, `pywebviewType=object`, `fontLoaded=true`, and
  `stageCount=5`. The adjacent `screen.png` exists and visually shows a
  rendered Persian right-to-left dashboard with cards and navigation. The
  recorded smoke test predates the newest EXE rebuild, so boot of that exact
  rebuilt binary is not established by this image.
  `screenshot.done=false` remains in the JSON; the presence of the image
  alone does not prove the screenshot callback reported completion.
- **Later exact-binary QA:** `RC1_EXECUTABLE_QA_20261020.md` documents a fresh
  execution of this rebuilt EXE in isolated AppData. Boot, Persian UI,
  task creation, title edit, checklist creation and restart persistence
  passed. Fresh full regression run using Python 3.12 passed (240 Python,
  17 JavaScript). A transient `Card not found` message appeared in the
  comments/attachment areas on the newly created task, then disappeared
  after reopening the executable; its cause remains unverified.

## Why development is not yet finished

**The build and automated regressions passed, but the release acceptance
criteria have not been fulfilled.** The gaps currently documented by
`RELEASE_QA_CHECKLIST.md`, `PRODUCT_REQUIREMENTS_2026-10-20.md` and
`INTEGRATION_03_05_REPORT.md` include:

1. Physical end-to-end operation on two Windows computers: authentication,
   project permissions, HTTPS/fingerprint configuration, concurrent edits,
   attachment transfers, offline changes, host restart and conflict recovery.
2. Real Google Drive for desktop sync, outage/reconnect and peer behavior;
   current tests simulate folder delivery. Multi-user peer identity/ACL
   through the shared folder remains outside the demonstrated scope.
3. A complete backup/restore rehearsal including accounts, user profiles,
   attachment binaries and data domains. SQLite covers four domains only;
   ordinary task JSON/Drive restore is narrower.
4. Manual UI testing of the packaged EXE for edits, board persistence,
   permissions, finance review, light/dark appearance and clean Windows
   startup. A rendered initial screen is insufficient to certify workflows.
5. Additional promised product features, including complete financial
   reporting/official invoice issuance and broader automation/UX functions,
   remain outside the verified RC1 acceptance scope. Decide and record the
   precise version boundary before declaring a stable 0.5 release.

## Continuation procedure

1. Use this checkpoint and `RELEASE_QA_CHECKLIST.md` as the starting point;
   do not reinterpret older preview README sections as the latest status.
2. Finish executable UI acceptance in a disposable AppData profile and
   record each attempted workflow, observed outcome and screenshot/log.
3. Resolve failures against the source, then rerun the affected regressions.
   For release-wide checks, run `py -3 scripts\release_qa.py --full` and
   retain its exit status and output. Rebuild with `npm run dist` after changes.
4. Exercise physical LAN/Drive scenarios and a complete recoverable backup
   set before a stable release designation. Mark scenarios **unverified**
   when hardware, credentials or accounts are unavailable.
5. Create a dated release evidence report with the new EXE's measured hash,
   test results, unresolved issues and actual release decision.

During this checkpoint's CoS status check, **no workers belonged to the
current caller**. That does not establish whether workers in other chat
sessions exist or whether any past session stopped for a specific reason.
There is no evidence here identifying a quota, tool failure or worker crash
as the cause of interruptions.
