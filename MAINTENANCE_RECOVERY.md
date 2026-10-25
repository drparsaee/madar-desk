# Madar Desk 1.0 | Offline maintenance CLI

**Maintenance only. No GUI, LAN endpoint, Google Drive upload, or default
APPDATA lookup.** The native app and its LAN server must be fully shut down.
All commands require an explicitly supplied **absolute** data root. The CLI
calls the existing `full_recovery.py` APIs, rather than implementing another
backup format.

## CLI contract (Windows PowerShell)

From the project's Python environment, with `psutil` installed:

```powershell
python -m maintenance_recovery backup `
  --data-root "D:\Offline-Madar\MadarDesk" `
  --archive "D:\Private-Backups\madar-full-20261021.zip" `
  --confirm-offline --acknowledge-plaintext

python -m maintenance_recovery restore `
  --data-root "D:\Offline-Madar\MadarDesk" `
  --archive "D:\Private-Backups\madar-full-20261021.zip" `
  --confirm-offline --acknowledge-plaintext

python -m maintenance_recovery recover `
  --data-root "D:\Offline-Madar\MadarDesk" `
  --confirm-offline
```

The archive must be outside the root, must already exist for restore, and
**must not** exist for backup. All commands return one JSON result to stdout
on success; refusal/error messages go to stderr. Exit codes: `0` success,
`2` CLI syntax error, `3` maintenance precondition refused, `4`
invalid/corrupt source/archive, rollback error, or another operation failure.

## Programmatic integration

```python
from pathlib import Path
from maintenance_recovery import (
    MaintenanceRefused, execute, pending_restore_journal,
)

# IMPORTANT: this startup check is READ-ONLY and must run BEFORE Bridge or
# any call to native_app.datadir() that could create files or start LAN.
root = Path(r"D:\Offline-Madar\MadarDesk")
pending = pending_restore_journal(root)  # -> Path | None
if pending is not None:
    raise RuntimeError("Recovery journal exists: refuse app startup until offline recovery")

# Explicit, privileged offline-only maintenance launcher:
report = execute(
    "backup", root, Path(r"D:\Private-Backups\madar-full.zip"),
    offline_confirmed=True, plaintext_acknowledged=True,
)
restored = execute(
    "restore", root, Path(r"D:\Private-Backups\madar-full.zip"),
    offline_confirmed=True, plaintext_acknowledged=True,
)
recovered = execute("recover", root, offline_confirmed=True)
```

The startup helper **does not** create a folder, open a database, trust journal
contents or infer APPDATA. If a pending journal is found, including a corrupt
one, native startup must **fail closed** until a separately launched offline
recovery command resolves it. A helper does not itself install a startup gate;
integrating it before native `Bridge` creation is a separate prime-agent task.

## Safety gates and limits

- Mandatory `--confirm-offline`, meaning *all* Madar instances, LAN hosts,
  schedulers, agents with write access and SQLite writers have been stopped.
  The flag is an explicit user attestation, **not** a mechanism that can force
  applications to stop.
- Mandatory `--acknowledge-plaintext` for backup and restore. **ZIP archives
  contain unencrypted LAN password hashes, financial records and attachment
  binaries.** Protect the destination with restricted permissions and
  authenticated encryption outside this tool. No secrets are sent to Drive.
- Paths with commonly known cloud-sync components, including Google Drive,
  My Drive, OneDrive, Dropbox and iCloud Drive, are **refused**; on Windows,
  known virtual-drive volume labels are also checked. This is a conservative
  *heuristic*, **not proof** that an arbitrary directory is not synchronized.
  Operators must independently verify the target is private and local. There
  is no `--allow-cloud` switch.
- An OS-held nonblocking **sibling maintenance lock** prevents simultaneous
  maintenance commands targeting the same data root. The file persists
  (one byte) to prevent unlink/recreate lock races. This lock does **not**
  coordinate with a native app that does not acquire it.
- A machine-wide process check refuses known native executable names
  `Madar-Desk*.exe`, `MadarDesk.exe` and Python/Pythonw processes explicitly
  running `native_app.py`, including apps using a different data root.
  Process-inspection failure or missing `psutil` causes **refusal**.
- A `BEGIN IMMEDIATE` probe with SQLite `busy_timeout=0` refuses when
  `madar-unified.sqlite3` or `attachment-storage/attachments.sqlite3`
  already has an active writer/lock, and does not initialize missing databases.
- **Limitation:** No external guard can prove that an unknown/uncooperative
  process has not modified an unlocked JSON file, or prevent an arbitrary
  writer from starting between a probe and the operation. Use a maintenance
  window with access controls and a single-process shutdown. This is
  conservative fail-closed detection, **not an absolute writer-exclusion
  guarantee**.

The underlying archive format still enforces ZIP-slip/symlink rejection,
per-file SHA-256 verification, attachment manifest and SQLite integrity
checks, 10,000-entry / 1 GiB total / 256 MiB-file ceilings, and
backup-first restore with a verified pre-restore ZIP. The previous complete
data folder remains at `preRestoreRoot` after successful restore. Interrupted
restores use a sibling recovery journal that must be resolved **before app
startup**. See [FULL_RECOVERY_API.md](FULL_RECOVERY_API.md).

## Test boundary

`python -m unittest tests.test_maintenance_recovery -v` uses disposable roots
under `tempfile.TemporaryDirectory`; it never operates on the user's real
APPDATA. The external subprocess test either performs a full round trip or
proves that it correctly refuses while unrelated real Madar executables
are running. All other focused operations use mocked process inventories
and real isolated SQLite/file-lock checks. No GUI or binary build is required.
