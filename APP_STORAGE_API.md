# Madar Desk unified SQLite storage (opt-in integration contract)

`app_storage.py` remains a standalone adapter and never resolves `%APPDATA%`
implicitly. The Windows host now exposes **explicit opt-in activation** via
`Bridge.enableUnifiedStorage()` and state via `Bridge.storageStatus()`.
Until activation, the legacy JSON files remain authoritative. Activation
backs up the original JSON bytes and initializes one SQL snapshot before
writing the activation marker. Once activated, Bridge task/collaboration/
finance/completion-outbox reads and writes use the SQL revision store.
Automation card events are applied into the collaboration domain in the same
revision as task changes. Existing legacy automation outbox entries may still
be replayed separately. The attachment binary store, LAN accounts and user
profiles remain separate.

The marker is `unified-active.json` next to `madar-unified.sqlite3` under the
app data folder. A missing or invalid database after activation prevents
startup rather than silently reverting to stale JSON. An orphan database
also blocks a repeat migration until deliberately reconciled. The host offers
full four-domain SQLite backups in its local backup list, but older JSON and
Google Drive task-only backups remain partial restores. This is a staged
opt-in upgrade, not a complete whole-application backup/restore mechanism.

## State contract and API

One atomic application revision contains exactly four domains:

| Key | Existing source file | Validation |
| --- | --- | --- |
| `tasks` | `tasks.json` | `data_model.normalize_plus` then `validate_plus` |
| `collab` | `collab.json` | `collab.validate_state` |
| `finance` | `finance.json` | `finance.validate_finance_state` (invoice hashes + ledger chain) |
| `completion_outbox` | `finance-completion-outbox.json` | strict list of completion event objects |

No partial bundle is accepted by `commit()`. The fourth domain is an array
with at most 10,000 entries, each with exactly `eventId`, `completionId`,
`cardId`, `projectId`, `actor`, and timezone-aware `at`. Event and completion
identifiers cannot repeat. A pending event can legitimately reference a task
that no longer exists: the host decides when replay is authorized, so storage
preserves unresolved records. **The storage adapter does not execute queued
financial commands, invoice actions, or collaboration commands.** Use existing
domain reducers under host authorization and commit their resulting state.

```python
from pathlib import Path
import collab
import finance
from app_storage import UnifiedAppStorage, RevisionConflict

# Synthetic example paths: Prime chooses actual paths only during integration.
store = UnifiedAppStorage(Path(r"D:\SafeSandbox\madar.sqlite3"))

# One-time migration. Every supplied JSON file is validated and copied to an
# immutable SHA-256-named backup before the first SQL commit.
initial = store.import_legacy(
    Path(r"D:\SafeSandbox\tasks.json"),
    collab_json=Path(r"D:\SafeSandbox\collab.json"),
    finance_json=Path(r"D:\SafeSandbox\finance.json"),
    outbox_json=Path(r"D:\SafeSandbox\finance-completion-outbox.json"),
    backup_dir=Path(r"D:\SafeSandbox\legacy-backups"),
)

current = store.load()  # UnifiedSnapshot or None before first commit
candidate = current.bundle  # a detached dict, safe to modify
candidate["tasks"]["tasks"][0]["title"] = "Edited"

try:
    updated = store.commit(candidate, expected_revision=current.revision)
except RevisionConflict:
    # Host must reload and resolve the concurrent change deliberately.
    latest = store.load()

copy = store.backup_database(Path(r"D:\SafeSandbox\backups\copy.sqlite3"))

# Creates a *new* revision with ALL four domains from a historic revision:
restored = store.restore(1, expected_revision=store.load().revision)
assert store.integrity_check()
```

Methods:

| Method | Exact behavior |
| --- | --- |
| `UnifiedAppStorage(db_path, *, timeout=5.0)` | Initializes **local** SQLite, schema version 1, WAL, FULL synchronous |
| `validated_bundle(bundle)` | Returns JSON-deep-cloned normalized/validated four-domain dictionary |
| `load()` | Returns `UnifiedSnapshot` or `None` if head revision 0 |
| `load_revision(revision: int)` | Historical detached snapshot, missing => `KeyError` |
| `commit(bundle, *, expected_revision: int)` | One `BEGIN IMMEDIATE`/CAS transaction for all four, or rollback; unchanged bundle => no-op revision |
| `restore(revision: int, *, expected_revision: int)` | Appends an auditable revision for all four old domains, even if content identical |
| `import_legacy(task_json, *, backup_dir, collab_json=None, finance_json=None, outbox_json=None)` | Verifies all provided JSON, backup-first source bytes, one import transaction with source manifest |
| `history(limit=100)` | Newest integer revisions, maximum limit 1000 |
| `integrity_check()` | SQLite integrity, contiguous revisions, SHA-256 content and domain validators |
| `backup_database(destination)` | WAL-consistent SQLite online backup; atomic publish to previously nonexistent path |

`UnifiedSnapshot` has `revision`, `bundle`, `sha256`, `created_at`, `source`.
Expected revisions are nonnegative integers, starting at `0` before the first
commit; `True` is rejected. App revisions are *not* interchangeable with LAN
revision hashes. `RevisionConflict`, `ImportConflict`, `AlreadyInitialized`,
`UnsupportedSchema` and `IntegrityError` are distinct errors. Invalid domain
data raises `ValueError` before writing anything.

## Import and crash safety

`task_json` is required. `collab_json`, `finance_json` and `outbox_json`
default to validated empty domain states **only if omitted (None)**. Explicitly
provided but missing/broken paths fail closed. A complete backup of every
provided original JSON byte stream is created in `backup_dir` as
`<domain>-<SHA-256>.json`, without overwriting any existing file, before
writing the first SQL snapshot or import manifest. The backing filesystem
must support same-directory atomic hard links and `fsync` for this guarantee;
unsupported backup destinations raise an error. A mid-backup failure can leave
some verified backups, but **no SQLite import**, and retry reuses those backups.

Once import succeeds, importing the identical set of **source bytes** again
returns the *current* latest revision and never reverts subsequent user edits.
Changed source bytes, including formatting changes, raise `ImportConflict`.
A database already initialized by a normal commit refuses legacy import.

Every SQL write stores one canonical four-domain JSON payload and its SHA-256
alongside immutable revision metadata. Snapshot insert, head CAS update and
(for migration) migration manifest are in one SQLite `BEGIN IMMEDIATE` /
`COMMIT`. On any error they roll back together. WAL recovery follows SQLite's
durability semantics, configured with `PRAGMA journal_mode=WAL` and
`PRAGMA synchronous=FULL`. The backup method uses SQLite's online backup API,
not direct copying of the live `.sqlite` file.

This design does not make the **old four JSON files** atomically editable.
After integration, SQLite must be the authoritative write path. Prime should
transition host readers/writers together instead of maintaining two independent
active authorities. Preserve existing auth, role checks and trusted completion
event verification in the host; persistence alone is not an authorization API.

## Integration notes and explicit limits

- Do not put the **live** SQLite file in a synced Google Drive folder, Dropbox,
  SMB share or another filesystem that cannot guarantee SQLite locks. Export
  consistent backups for later copying instead. This module does not upload.
- Keep legacy `task.checklist` and named `task.checklists`, `task.status` and
  `task.listId`, and `task.labels` and `task.labelIds` consistent at the host
  write boundary. The normalizer cannot infer which divergent view is newer.
- For a card completion, Prime should derive the verified completion event,
  update task state and outbox, call authorized `finance.apply_finance_command`
  where appropriate, then `commit()` the complete resulting four-domain bundle
  using the revision loaded before the domain operations. Treat revision
  conflicts as retry/rebase decisions, **not** silent last-write-wins.
- Source import does not include LAN credentials, local profiles or encrypted
  Google OAuth tokens. Account backup/migration is a separate decision.
- Tests cover synthetic Windows paths, process termination before commit,
  failure injection in DB and backup publication, WAL reopen, CAS concurrency,
  finance ledger hashes and collaboration command records. Physical power
  failure, real OAuth, multiple Windows clients and a switched native EXE have
  **not** been tested in this worker task.

## Verification commands

```powershell
python -m unittest discover -s tests -p test_app_storage.py -v
python -m compileall -q app_storage.py tests/test_app_storage.py
npm test
```

All tests create temporary synthetic inputs and paths. They do not call
`native_app.datadir()` or touch a user's actual `%APPDATA%`.
