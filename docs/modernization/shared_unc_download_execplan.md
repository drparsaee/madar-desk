# Shared UNC link and download: execution plan (2026-11-02)

## Purpose / owner decision / exclusions
- Owner requires users of each Windows Madar client to save a file published through an existing SMB/UNC share. UNC share names can contain spaces (synthetic example `\\\\FILESERVER\\Scan Drive\\sample\\مهر\\English.zip`).
- Owning checkout: `D:\CoS-Test\madar-desk`, baseline `aa99f21067d3c87aec392c05e933c905dbac1e36` on `main`; private LocalForge `origin` is canonical.
- Do not touch live user/task/Parsian data, installed executable, LAN access control, updater, backups, or untracked research folders.

## Existing behavior / entry points
- `SharedLinks` in `src/productivity.jsx` rejects spaces in the share name and calls `api.openSharedFile` when either file name or Explorer button is clicked.
- `native_app.valid_share_path` accepts spaces in share names, rejects traversal and device namespaces; `Bridge.openSharedFile` sends Explorer `/select,` which selects a file without downloading it.
- The native bridge method is exposed through `JS_BRIDGE`, while web-only `mockBridge` in `src/App.jsx` has an explicit unsupported response.
- Links are stored as `fileLinks` path/name/id metadata; file bytes remain on the shared drive. No schema change.

## Work plan and parity
1. Add frontend and native characterization tests, run to show frontend's rejected spaced share path.
2. Align frontend path validation with backend security rules; retain UNC requirement, traversal and device namespace denial.
3. Add explicit native download to client's Downloads folder with collision-safe naming, local SMB permissions, and no execution of downloaded data. Preserve independent `openSharedFile` Explorer action.
4. Run focused UI/native tests, full safe source suite and diff check. Commit/push only on passing gates and no conflict with other agents.

## Normal, edge, denial, repeat scenarios
- Space-bearing Share with Persian directory and ZIP filename: accepted by UI and native; copied bytes saved on the local client machine.
- Repeated download of same filename: original preserved; unique extra local copy created. Interrupted copy: incomplete local file removed.
- Traversal (`.`/`..`), URL, drive path, device UNC, invalid characters, missing share, unsupported directory downloads: fail with visible error; never execute shared content.
- SMB authorization is decided by Windows permissions on each client. Files never transmit through the Madar LAN API or enter app state, and file links remain metadata-only.

## Progress
- `VERIFIED`: reproduced red baseline in JS (5/6) followed by green focused JS (6/6) and native (23/23), safe full source runner passed 2026-11-02 (Python 1,658 reported; Node 530/530; Vite build succeeded). Python reported 2 skipped and 2 expected failures, no unexpected failures/errors.
- `VERIFIED`: Windows Downloads known folder resolved as an existing absolute folder (read-only lookup); `git diff --check` succeeded.
- `IN PROGRESS`: private LocalForge commit/push status is tracked by Git refs and worker handoff, separately from source QA.
- `BLOCKED` pending separate real-device acceptance: package new EXE and manually check SMB downloads on each actual client.

## Surprises / decisions
- Observed 2026-11-02: Explorer `/select,` alone does not save a file; implement a separate download operation while retaining the Explorer action.
- Local installed EXE behavior on both actual Windows PCs cannot be asserted from synthetic fixtures.

## Validation and acceptance
- Frontend regression, native validation/security and copying tests; full isolated `python -B tools/safe_test_runner.py` and `git diff --check`.
- Actual two-client SMB file download and installed EXE activation require separate release and user acceptance gates; no production effects in this plan.
