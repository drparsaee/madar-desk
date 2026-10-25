# Madar Desk P0: solo local state CAS regression

## Evidence and exact boundary

**Status: original stale overwrite reproduced; Prime integrated a repair during this worker run and the focused contract suite now passes.**
The new `tests/test_local_state_cas.py` creates **two independent `native_app.Bridge()` objects pointing only at a unique `TemporaryDirectory` per test**. Both capture editing snapshots via the new `getStateForUi()`. First Bridge saves a change to `example-2.title`, `example-2.cost` and `p-sample.price`. Second Bridge then attempts to save a previously captured state with only a different card (`example-3.title`) changed.

Observed **before Prime's integration**: the second save was accepted and the first writer's card title, cost and project price were **erased** under both solo JSON and opted-in SQLite. This was a deterministic sequential reproduction: no parallel threads or OS race needed. Prime added token-bearing `getStateForUi()`, process-shared CAS guard, and a missing-token check once a Bridge has served UI state. With these changes, **the stale rejection tests and missing-token UI tests now pass**.

The low-level `UnifiedAppStorage.commit(bundle, expected_revision=<read revision>)` already rejects a stale caller-supplied revision (`app_storage.RevisionConflict`). Before the new host guard, the higher `Bridge` discarded the UI read baseline and committed against the newly fetched SQLite `current.revision`. JSON likewise replaced the file unconditionally. Prime has since added `_state_write_guard` and a hash comparison for `expected_local_revision`. A Bridge that served `getStateForUi()` rejects tokenless saves with a `CONFLICT` error. Legacy non-UI callers may omit the token but use the Bridge's last observed local revision as a fallback, which is outside the strict UI-token contract. The new OS file lock coordinates cooperating local writers.

Source inspection context (before / after Prime's concurrent integration on 2026-10-21):

- `native_app.py:getStateForUi`: added by Prime; returns a UI-only `__localRevision` SHA-256 of normalized task state. `getState()` remains a metadata-free LAN/backup read.
- `native_app.py:saveState`: now passes the UI token to `_save_local_state(expected_local_revision=...)`, rejects missing token after `getStateForUi()`, and uses the last locally observed version for legacy non-UI callers.
- `native_app.py:_save_local_state`: checks the normalized state hash inside `_state_write_guard`; JSON replaces state and SQLite still commits with the latest database head after the earlier hash comparison. Cross-process concurrent SQL-domain writers require their own coverage.
- `app_storage.py:345–369`: real low-level transactional compare-and-swap is available, and passes a direct stale-revision control.
- `src/App.jsx:435–459`: state is read into React state and autosaved later; current handler updates `__remoteRevision` after a save and must preserve a distinct local token once added.

## Minimum safe, reviewable repair contract for Prime

1. **Issue a revision on a UI-specific read, keeping raw state pure.** Prime chose `getStateForUi()`, which returns `__localRevision` from `lan.revision(state)` while `getState()` stays free of this UI metadata. The version must describe the *same* authoritative state snapshot returned to the editor. Two readers of unchanged state receive the same token, and a write changes it. Metadata must never enter stored JSON, LAN responses or backups. A backend-qualified version could additionally prevent token reuse after JSON-to-SQLite migration; this guard has not been included in the current test contract.
2. **Demand the expected local revision for the normal UI save path**, e.g. the `__localRevision` inside the submitted snapshot. Reject missing, malformed or stale tokens with a stable `CONFLICT`-prefixed error before changing files, backups or outboxes. Prime implemented this for Bridges that have entered `getStateForUi()` mode. For compatibility, tokenless **non-UI** saves currently use that Bridge's last observed local version; Prime should confirm this legacy path is restricted to trusted callers and cannot be accidentally invoked by a user-supplied stale snapshot.
3. **JSON requires a process-shared lock** covering current-file read/fingerprint comparison, related side-effect preparation, and atomic replacement. `Bridge._lock` is insufficient when two Python processes use the same APPDATA. A compare performed before releasing a lock and subsequent write without it is subject to TOCTOU. Keep unchanged writer-visible state on conflict; avoid creating an outbox entry or implicit backup from rejected data. Preserve current flush/fsync/replace behavior and Windows cleanup/lock-release safety.
4. **SQLite must enforce the caller's editing baseline through the commit boundary**. Prime currently checks an SHA-256 task-state token inside a process-shared lock and then commits using the latest SQLite head, which fixes the tested two-Bridge stale-write case. It is still necessary to verify true cross-process SQLite updates that do not cooperate with the same lock, concurrent finance/collaboration operations, and changes between hash-check and commit. All generated journal/receipt/completion effects from a rejected card update must remain unapplied.
5. **Return the new local revision after success** (Prime currently returns `localRevision`) and update the React state baseline to it. If edits arrived while the request was pending, retain them and retry their *new* snapshot against the updated revision without clobbering subsequent edits. Treat a conflict as blocked autosave with reload/resolve/export recovery. Keep the local `localRevision` success field distinct from the existing `result.revision` LAN response. UI wiring and separate UI acceptance are Prime's responsibility.
6. **Keep network/offline semantics independent**. `__remoteRevision` means the LAN server's per-account view revision, and `__offline` identifies a client operating from cached LAN state. Neither is a local file/storage revision. `__localRevision` applies only to solo/host-local interactive state; it must not authorize writes to the LAN server or bypass the existing offline reconciliation path. A later JSON-to-SQLite storage migration invalidates earlier JSON tokens.

The existing `storageStatus().revision` API is **not sufficient** to protect UI writes: a separate status call can race with the UI snapshot and is not attached to that exact state; JSON mode has no storage revision number. A fresh `getState()` just before `saveState()` is equally insufficient if it silently replaces the caller's real editing baseline.

## Regression execution and verification

```powershell
py -3.12 -m unittest tests.test_local_state_cas -v
```

The **initial reproducer** (before Prime's changes) ran on Python 3.12.10 with **7 executed, 3 PASS, 4 FAIL** (1.028 seconds). This confirmed actual loss of first-writer card title, cost and project price in both JSON and SQLite. Two extra missing-token regressions were then added and the suite was adapted to Prime's `getStateForUi()` contract.

The **latest focused run after Prime integration**: **10/10 PASS** (1.309 seconds) with `py -3.12 -m unittest tests.test_local_state_cas -v`. `py -3.12 -m compileall -q tests/test_local_state_cas.py` also passed. Exact current coverage:

| Test | Observed result | Meaning |
| --- | --- | --- |
| `test_json_get_state_for_ui_issues_stable_cas_revision` | PASS | UI revision issued while `getState()` remains pure |
| `test_sqlite_get_state_for_ui_issues_stable_cas_revision` | PASS | UI revision issued in SQLite mode |
| `test_json_save_requires_caller_provided_local_revision` | PASS | UI-session token stripping cannot bypass JSON CAS |
| `test_sqlite_save_requires_caller_provided_local_revision` | PASS | UI-session token stripping cannot bypass SQLite CAS |
| `test_json_stale_second_bridge_must_not_erase_first_writer` | PASS | JSON preserves first writer's title, cost and price |
| `test_sqlite_stale_second_bridge_must_not_erase_first_writer` | PASS | SQLite preserves first writer's title, cost and price |
| `test_json_one_writer_can_save_and_reopen_without_losing_cost` | PASS | Normal JSON save and reload retains cost |
| `test_sqlite_one_writer_can_save_and_reopen_without_losing_cost` | PASS | Normal SQLite save and reload retains cost |
| `test_underlying_sqlite_storage_cas_rejects_actual_stale_head` | PASS | Low-level SQLite CAS rejects actual stale head |
| `test_json_backup_and_raw_read_exclude_ui_revision_metadata` | PASS | Backup JSON and raw `getState()` omit UI-only token |

All ten tests create their own `TemporaryDirectory`, patch `APPDATA` and `LOCALAPPDATA`, and patch `native_app.datadir()` to the same disposable directory, with explicit assertions that each Bridge path remains under that temporary root. The two Bridge objects inside each test intentionally share *only that test's* temp root; test cases do not share a database or user data with each other. Windows database connections are closed by the existing storage context managers; cleanups restore environment and remove the temporary root.

**Unverified:** true parallel process/lock contention, migration-related token invalidation, trusted legacy tokenless calls, recovery after power failure, UI autosave races with edits during a pending request, LAN offline resynchronization, installer/runtime smoke tests, and full application suite. These are separate Prime acceptance gates. The worker did not modify `native_app.py`, `app_storage.py`, `src/App.jsx`, runtime APPDATA, Git, or production/release assets.
