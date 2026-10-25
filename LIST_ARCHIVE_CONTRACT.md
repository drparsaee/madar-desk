# BD13 list archive: isolated Python persistence and LAN contract

Scope: **new Python regression tests only**, no changes to release/runtime assets. `tests/test_list_archive_contract.py` exercises JSON/opt-in SQLite persistence and direct `LanService` methods on a disposable `TemporaryDirectory` for each test. It never starts a LAN listener or accesses real APPDATA. Each fixture patches both APPDATA/LOCALAPPDATA and `native_app.datadir()` and asserts Bridge paths are within the disposable root.

## Data contract

`board.stages[]` retains every original stage and its order. Its optional `archived` field, when present, must be **exactly boolean**. Archiving a board-local list changes only that stage's flag; no card migration, deletion, `listId`/`status` rewrite, `cardOrder` reset, checklist price reset, or automatic `task.archived` toggle. Global `stages`, other boards, project prices and the actual `finance` domain remain intact. Restoring a list sets that stage's flag back to `false`, retaining its ID and cards. Legacy stage objects without `archived` must continue loading.

The tests include an archived card (`task.archived=true`) and a separate card attached to the archived board-local list; the two concepts remain distinct. They verify persistence after a **fresh Bridge** reopen for both legacy JSON and explicitly enabled SQLite storage. SQLite integrity is checked. A separate finance contract is created and the stored `finance` state compared through archive and restore. Invalid archive flags are rejected before replacing storage or altering finance.

## LAN contract

An admin can archive and restore a board-local stage through `LanService.write_state` with a matching view revision. The editor can read the stage status and edit an authorized card while retaining its archived stage; the editor cannot change the board structure, and the viewer cannot write. Project grants filter boards and cards; non-admin project prices remain masked. A stale admin revision must return `CONFLICT` and leave committed data unchanged.

The JS module `src/listarchive.js` enforces the `canManage` UI gate, idempotence, and refusal to archive the **last active list**. The host independently enforces that invariant in `data_model._check_list`, since UI-only guards can be bypassed. The regression `test_python_rejects_every_stage_archived_and_retains_original_state` checks this fail-closed behavior and unchanged task references.

## Evidence, 2026-10-21

Commands executed in `D:\CoS-Test\madar-desk`:

```powershell
py -3.12 -m unittest tests.test_list_archive_contract -v
node --test tests/listarchive.test.cjs
py -3.12 -m compileall -q tests/test_list_archive_contract.py
```

Initial focused Python result: **10 tests, 9 PASS, 1 ERROR** in 8.109 seconds. The error reflected a mistaken test assumption that Python should allow all columns archived; the safer contract requires host validation. The test has since been revised; record the result of the subsequent test run separately. `node --test tests/listarchive.test.cjs` was **16/16 PASS** and Python `compileall` passed.

This verifies data-model logic, Bridge persistence and in-process LAN access only. It **does not verify React interaction, packaging, an installer, physical LAN clients, or RC2 EXE**. In particular the existing RC2 EXE has not been shown to include BD13.
