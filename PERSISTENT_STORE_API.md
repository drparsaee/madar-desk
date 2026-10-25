# Madar Desk: independent SQLite persistence adapter

This is the integration contract for `data_model.py` and `persistent_store.py`.
The running Windows host still owns the active JSON file and LAN endpoints;
these modules do **not** switch that host to SQLite or access `%APPDATA%`.
Choose database/backup paths explicitly. Both modules use Python's stdlib.

## Data model contract

```python
from data_model import normalize_plus, validate_plus

enhanced = normalize_plus(existing_v1_state)  # pure, idempotent, deep copy
validate_plus(enhanced)                       # True or path-specific ValueError
```

The existing `version == 1`, `projects`, `tasks`, `stages` and settings stay
present. Added structures are `workspaces[]`, `boards[]` (each board owns
`stages[]`, `labelDefinitions[]`, and `customFields[]`), `templates[]`, and
`tasks[].boardId`, `listId`, `archived`, `labelIds`, named `checklists[]` and
`customFieldValues`. Every existing project gets a stable, linked board.

`normalize_plus` retains the old flat `task.checklist` byte-for-byte at the
JSON-value level. It allocates stable and unique IDs for missing/duplicate
legacy checklist item IDs, reserving valid originals first to avoid hashing
collisions. On *recognized generated* named groups (`checklist-legacy` and
`checklist-legacy-*`), malformed item IDs and repeated/missing group IDs are
repaired before strict validation. New custom groups with missing IDs still
raise `ValueError`. Unknown JSON keys are preserved.

Compatibility requirement for host/UI integration: maintain both halves when
editing `task.status` / `task.listId`, `task.checklist` / `task.checklists`, and
`task.labels` / `task.labelIds`. The normalizer does not guess which divergent
half is newer. Legacy global stage IDs and board-local column IDs can differ.

## SQLite API

```python
from pathlib import Path
from persistent_store import SQLiteSnapshotStore, RevisionConflict

store = SQLiteSnapshotStore(Path(r"D:\SomeSandbox\madar.sqlite3"))

# Optional one-time migration after reading a user's legacy JSON file:
first = store.bootstrap_from_json(
    Path(r"D:\SomeSandbox\tasks.json"),
    backup_dir=Path(r"D:\SomeSandbox\legacy-backups"),
)

current = store.load()  # Snapshot | None, revision 0 means uninitialized
if current is not None:
    proposed_state = current.state  # independent decoded dict, safe to edit
    proposed_state["tasks"][0]["title"] = "Edited title"
    try:
        updated = store.save(proposed_state, expected_revision=current.revision)
    except RevisionConflict:
        # Reload and merge intentionally; a stale write never silently wins.
        newer = store.load()

# Safe point-in-time backup; destination MUST NOT exist.
database_copy = store.backup_database(Path(r"D:\SomeSandbox\backup.sqlite3"))

# An existing historical revision can be restored by appending a NEW revision.
snapshot = store.restore(1, expected_revision=store.load().revision)
assert store.integrity_check()
```

`SQLiteSnapshotStore(db_path, *, timeout=5.0)` creates a new schema on an
empty SQLite database. It rejects unsupported future versions and databases
containing unrelated tables. `PRAGMA user_version` is `1` for this persistence
schema; this is independent of the Madar JSON `state.version == 1`.

| Operation | Result / semantics |
| --- | --- |
| `load()` | Latest committed `Snapshot` or `None` |
| `load_revision(revision)` | Historical `Snapshot`, missing => `KeyError` |
| `save(state, *, expected_revision)` | Validated, normalized, atomic immutable append, CAS; identical payload is a no-op |
| `restore(revision, *, expected_revision)` | Append a new head containing the chosen older state |
| `bootstrap_from_json(path, *, backup_dir)` | Immutable original-byte backup first, then one transactional import (revision 1) |
| `backup_database(destination)` | Consistent copy via SQLite backup API; never overwrites |
| `history(limit=100)` | Latest revision numbers, max 1000 |
| `integrity_check()` | SQLite structural check plus every snapshot's SHA-256 and data schema |

A `Snapshot` has `revision: int`, `state: dict`, `sha256: str`,
`created_at: str`, and `source: str`. `RevisionConflict`,
`StoreAlreadyInitialized`, `MigrationConflict`, `UnsupportedSchemaError` and
`SnapshotIntegrityError` identify different failure paths. Invalid data raises
`ValueError`. Snapshot revisions are local integer counters starting at 1,
not the old LAN hexadecimal/hash revision and not an HTTP synchronization API.

## Transaction and backup guarantees

- Writes use `BEGIN IMMEDIATE` + `COMMIT` for both immutable snapshot insertion
  and updating the sole `head` row. All failures `ROLLBACK`. WAL mode and
  `synchronous=FULL` are enabled for local-disk durability.
- A legacy migration reads at most 15 MB of strict UTF-8 JSON, validates and
  normalizes it in memory, makes a content-addressed immutable backup with
  `fsync`, then writes the snapshot *and* migration record atomically. It never
  edits, renames, or removes source JSON. If SQL fails after backup publication,
  the backup deliberately remains as an intact recovery artifact.
- Repeating migration with exactly the same input bytes is safe and returns
  the current snapshot, including subsequent user edits. Different source
  bytes after migration raise `MigrationConflict` and cannot overwrite data.
- Backup publication requires same-directory atomic hard links. Unsupported
  filesystems fail closed; callers can choose a supported local backup volume.
  `backup_database()` uses the SQLite online backup API, not a raw copy of a
  potentially active WAL database.
- This stores full snapshots and full history; there is no automatic revision
  pruning. Retention, quota strategy, LAN auth, OAuth, conflict resolution and
  credential/profile migration belong to future integration decisions.
- SQLite's write locking requires a local supported filesystem. Do not put the
  **live** SQLite database directly inside a Google Drive sync folder or SMB
  network share. Store consistent backups there after creation instead.

## Automated Windows tests (sandbox paths only)

```powershell
python -m unittest discover -s tests -p test_data_model.py -v
python -m unittest discover -s tests -p test_persistent_store.py -v
```

The tests use `tempfile.TemporaryDirectory` and explicit paths. They cover
legacy ID repair/idempotency, source preservation, atomic head rollback,
abrupt process exit before commit, concurrent revision CAS, concurrent imports,
immutable backup behavior, schema version refusal and checksum tampering.
They do not demonstrate physical LAN collaboration, real Google OAuth, power
loss on target storage hardware or compatibility with an EXE not wired to this
adapter.
