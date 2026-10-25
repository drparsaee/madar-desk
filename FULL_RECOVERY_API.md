# Madar Desk: Explicit offline full-domain recovery

## Scope and safety conditions

This **opt-in, local-only Python API** builds a ZIP containing the supported
application data domains. It is not wired into the native bridge, LAN endpoints,
Google Drive, or the user interface. The caller supplies **explicit absolute**
paths. The module never discovers or selects APPDATA itself.

**SECURITY WARNING: ARCHIVES ARE NOT ENCRYPTED.** LAN account password
**hashes**, invoices, financial records, avatars and attachment contents are
stored inside the ZIP. A hash is not a plaintext password, but it is still
credential material. Save archives only to restricted local storage and use
independent, authenticated encryption (for example, an encrypted volume) before
any off-machine transport. Do **not** put archives in Google Drive, a synced
folder or a public share as a default. Encrypted portable archive support is
not claimed or implemented; the project's Python environment did not have
`cryptography` installed during implementation.

All three APIs require `offline=True`: **stop the Windows application, LAN
host, background schedulers and all other writers first**. This flag is a
declaration from the integrator, not a reliable process-lock detector. Never
invoke a restore inside a running `Bridge`/webview instance. Do not restore
over a user's real APPDATA when testing. The functions do not create, open or
inspect an unrequested APPDATA location.

## Public API

```python
from pathlib import Path
from full_recovery import (
    RecoveryError, create_full_backup, restore_full_backup,
    recover_interrupted_restore,
)

root = Path(r"D:\Isolated-Test-Data\MadarDesk")  # EXPLICIT and offline
archive = Path(r"D:\Isolated-Backups\2026-10-21-full.zip")  # NEW, outside root

backup = create_full_backup(root, archive, offline=True)
# -> {path, files, bytes, manifestSha256}

# With all instances stopped, recover any previous interrupted restore FIRST:
recovery = recover_interrupted_restore(root, offline=True)
# -> {recovered: False} or {recovered: True, path: ...}

restored = restore_full_backup(root, archive, offline=True)
# -> {path, files, bytes, preRestoreArchive, preRestoreRoot}
```

Restore is an intentional destructive **logical replacement** of managed data,
not a merge. The original data directory is preserved as the sibling named in
`preRestoreRoot` (including unknown/unmanaged files), and a separate verified
pre-restore ZIP at `preRestoreArchive`. Those copies can contain private
credentials; move/store them securely. The operation does not silently delete
them. Restoration requires an existing readable source root to produce a
backup-first rollback copy. Never point the archive under the source root.

## Data covered

- In legacy JSON mode: `tasks.json`, `collab.json`, `finance.json`,
  `finance-completion-outbox.json` (all four are validated as one bundle);
  optional absent side domains receive their existing empty defaults.
- In active SQLite mode: `unified-active.json` and **consistent online SQLite
  backup** of `madar-unified.sqlite3`; all revision history, finance,
  collaboration, tasks and completion outbox are retained together. Auxiliary
  legacy JSON files, if present, are carried as-is.
- Additional standalone state: `automation-card-outbox.json`,
  `lan-users.json` (roles, project grants, profile details and password
  hashes), `personal-profile.json` and `preferences.json`.
- Attachments: consistent snapshot of
  `attachment-storage/attachments.sqlite3`, audit/idempotency records,
  all referenced binary `attachment-storage/blobs/<prefix>/<sha256>` and the
  attachment store's independently verified manifest.

Not included: `lan-login.bin`, `google-auth.bin`, `cloud-peer-code.bin`,
`lan-connection.json`, `lan-profiles-cache.json`, live sessions and transient
LAN credentials, offline client caches/sync folders, TLS private-key files,
other unrelated root files or previous backup collections. These are
intentionally excluded to avoid exporting tokens and device-specific DPAPI
material. After cross-device restoration, configure LAN/Drive credentials and
TLS settings afresh. A full-domain backup is **not** a whole-computer clone.

## Archive integrity and limits

Archive uses ZIP_STORED (no compression), a strict UTF-8 `manifest.json`, and
SHA-256 + exact byte length for every archived file. File list must match the
manifest exactly. Restore refuses duplicate/case-colliding names, absolute
paths, `..`/Windows drive and ADS paths, backslashes, unrecognized filenames,
ZIP symlink/device entries, compression (including zip bombs), encrypted ZIP
entries, bad hashes, malformed JSON, invalid LAN accounts, missing blobs and
SQLite integrity failures. Limits: up to **10,000 files**, up to **256 MiB per
file**, up to **1 GiB total contents**, and **2 MiB manifest**. This bounded
version intentionally refuses larger archives rather than risking unbounded
memory, disk or verification time.

Archives are self-checksummed, **not signed**: a local attacker who can replace
an archive *and* its manifest can produce another structurally valid archive.
Authenticity requires trusted access controls or a separate signature.

## Crash-safe restore protocol

1. Validate every ZIP entry and extract to a unique sibling staging directory;
   validate four-domain state, LAN grants and attachment DB/blob hashes there.
2. Produce a **new verified pre-restore archive** of the existing root before
   modifying it. Abort if existing domain state is damaged.
3. Write and fsync a restricted sibling recovery journal. Atomically rename the
   original root to `.madar-restore-old-<token>`, then rename staging to the
   original root. The two renames are **not one atomic filesystem operation**.
4. On ordinary errors after the first rename, run rollback immediately. On
   abrupt power/process interruption, call
   `recover_interrupted_restore(root, offline=True)` **before starting Madar**.
   If a valid original directory exists, recovery restores it and removes only
   its own staging directory. Ambiguous/untrusted journal state fails closed.
5. On success, keep both the old root and pre-restore ZIP. Remove the journal.

Crash-recovery is **explicit**, not automatically installed on application
startup, because modifying `native_app.py` or startup flows is outside this
worker's ownership. The prime integrator must implement a startup recovery gate
before enabling GUI restore. Directory-rename guarantees assume a single local
filesystem; open Windows handles and concurrent writers can block the swap.

## Integration notes

The present API is meant for offline maintenance or an external privileged
launcher after process shutdown. Before production integration: display a
strong plaintext-archive warning, request explicit user approval, validate
available disk space, enforce a single-process maintenance lock, choose an
encrypted destination where practical, and call recovery before launching any
writer. Never expose these APIs on a LAN endpoint or to non-administrators.
