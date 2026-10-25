# Madar Desk 1.0 RC1 — backup scope honesty (P0)

## Purpose and status

A named **local backup file** must not be presented to its user as a complete
Madar application backup when it omits identity records, attachment binary
data or the device-local personal Planner. The one-click backup is still a
valid snapshot of a **specific subset** and remains useful for recovery of
that subset.

The Python host's implementation and React UI wording are owned by Prime;
this worker created only the independent acceptance tests
`tests/test_backup_scope_truth.py` and this document.

## Current native host contract

Method: `Bridge.createLocalBackup() -> dict`, exposed in the Windows
`window.madar.createLocalBackup()` bridge. It is **host-only**: a network
client is refused before a backup directory is created.

Both modes return at least:

~~~python
{
    "name": "<safe saved filename>",
    "path": "<path inside host's local backups directory>",
    "complete": False,          # Boolean. Never True.
    "scope": "<specific subset>",
    "omitted": ["<omitted data kind>", ...],
    "note": "<non-empty, human-readable explanation>"
}
~~~

| Mode | `scope` | Backup body | Explicit omissions |
| --- | --- | --- | --- |
| JSON / legacy | `task-state-only` | A valid `tasks.json`-shaped state (projects, boards, lists, tasks, and their embedded task fields) | `finance`, `collaboration`, `attachment-binaries`, `planner-local-storage`, `lan-accounts`, `login-credentials` |
| Opt-in SQLite | `sqlite-domains-only` | Consistent SQLite snapshot of transactional task, collaboration, finance and completion-outbox domains (and automation if enabled) | `attachment-binaries`, `planner-local-storage`, `lan-accounts`, `login-credentials` |

The exact identifiers and the `omitted` field are public API contract fields.
An older interim implementation used `unified-sqlite-domains-only` and
`excluded` with no `note`; clients/test fixtures must not silently substitute
those names. No old field aliases or automatic migration are implemented by
this worker. The current bridge tests validate the above target shape.

**Important distinction:** The JSON task state can contain limited card
metadata, e.g., a title and a link to an attachment, but the **attachment's
binary data is still absent**. Thus not even an otherwise intact task backup
is sufficient to restore its original files. Likewise, login credentials and
LAN user records are different data domains. Local Planner contents live in
WebView storage, not in the host's JSON or SQLite archive.

### GUI disclosure

`src/App.jsx` displays an explicit
`<aside role="note">` headed “محدوده واقعی پشتیبان‌ها” in the backup/settings
area. It states the JSON and Drive copies cover primarily task/board state,
the SQLite backup omits attachment binaries and LAN accounts, and the personal
Planner is outside these modes. The UI points advanced operators to
`maintenance_recovery.py` for an offline broader archive.

The UI warning is static: the `listLocalBackups()` metadata list currently
contains name and size only, not the per-file `scope`/`omitted` fields. A
new GUI feature rendering richer per-backup metadata would require its own
versioning/compatibility checks; it is **not** part of this P0 assertion.
Similarly, a note attached to a successful return does not itself change
the behavior of older clients that only read `name` and `path`.

## Distinguishing broader offline recovery

`full_recovery.py` and the guarded `maintenance_recovery.py` CLI implement
separate full-domain offline ZIP backup and restore with explicit paths,
integrity validation, pre-restore snapshot and crash-recovery journal. When
supported and present, the archive can include **host LAN account records,
the attachment database and binary files, alongside task/collaboration/
finance data**. This is *not* a one-click GUI snapshot and must not be
substituted with a bare `.sqlite3` file.

See `MAINTENANCE_RECOVERY.md` for commands requiring a stopped Madar/LAN host,
explicit data-root and archive paths, `--confirm-offline` and
`--acknowledge-plaintext`. **ZIP backups are not encrypted**; never place
them unprotected in cloud-synced folders. Authentication session secrets
and device-specific credentials are intentionally excluded from recovery.
The Planner's browser localStorage remains separate; the broader CLI is not
claimed to recover it.

No real APPDATA/LOCALAPPDATA, Google Drive, physical LAN, production ZIP or
Windows EXE was used by these acceptance tests.

## Acceptance tests and fixture design

Entry point:

~~~powershell
cd D:\CoS-Test\madar-desk
python -m unittest discover -s tests -p test_backup_scope_truth.py -v
~~~

The test suite creates one disposable directory per test; patches
`native_app.datadir` and child process `APPDATA` / `LOCALAPPDATA` to
disposable locations; constructs a real offline `Bridge` in solo mode,
without LAN listen, EXE, Google OAuth or external networking.

The tests verify:

1. **JSON truth + usability:** no false `complete`, exact
   `task-state-only`/`omitted`/`note` contract; real JSON file equals
   the pre-backup task state; task restore roundtrip works; distinct synthetic
   LAN identity and attachment bytes are not exported or changed.
2. **SQLite truth + integrity:** explicit in-fixture migration to unified
   SQLite; a real collaboration comment; `UnifiedAppStorage.integrity_check()`
   passes on the backup; its revision, SHA-256 and full stored bundle match
   the source; later live commits do not mutate the exported SQLite file.
   Accounts, blobs and personal Planner remain absent.
3. **Neither mode becomes 'complete' merely because there are no attachment
   files**; partial omissions describe the format contract, not only the
   currently populated records.
4. **Client refusal** happens before local backup directory creation.
5. Source guard rejects any reintroduction of `"complete": True` in
   `createLocalBackup`, and checks the `scope`, `omitted`, `note` contract.
6. Static UI source guard checks visible Persian disclaimer mentions Google
   Drive, SQLite, file attachments, LAN identities, personal Planner,
   `maintenance_recovery.py` and the unencrypted ZIP warning. It does not
   assert pixel appearance or actual end-user interaction.

### Observed results

**21 October 2026:** `python -m unittest discover -s tests -p
test_backup_scope_truth.py -v`: **6 tests, 6 PASS, 0 failures/errors,
exit code 0**, approximately 0.55 seconds. During the first attempt against
the temporary interim host shape, five test methods failed on
`scope`/`excluded`/`note` naming. Once Prime aligned the production bridge
to `sqlite-domains-only`, `omitted` and `note`, the same strict contract
checks passed. No source or existing test files were changed by this worker.

## Limits of this gate

This P0 test establishes that **the quick-backup files are intact for their
declared subset and are no longer mislabeled complete**. It does not prove
a full system restore including attachment bytes, LDAP/remote identity,
Windows credential portability, multi-computer recovery or disaster
recovery. All of those require separate system-level acceptance and
permission checks. The release remains RC until the other safety gates close.
