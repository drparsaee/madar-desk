# Madar Desk: secure binary attachment service

`attachments.py` is a standalone Python 3.12 **host-side** module providing
authorized binary storage. It does not add LAN routes or UI controls and does
not open Madar's real `%APPDATA%` directory. The host must choose its own
storage directory and authenticate users before calling the service.

## Exported API

```python
from attachments import (
    AttachmentStore, AttachmentError, SCHEMA_VERSION,
    MAX_UPLOAD_BYTES, MAX_REQUEST_BASE64,
    MAX_IMAGE_PREVIEW_BYTES, MAX_TEXT_PREVIEW_BYTES,
)

store = AttachmentStore(host_selected_absolute_directory)

# Derive `actor` from a verified session, not POST body.
principal = lan_service.account_for(session_token)
context = dict(
    actor=principal["username"],
    accounts=lan_service.users,                 # authoritative host accounts
    cards=bridge.getState()["tasks"],           # authoritative host cards
    projects=bridge.getState()["projects"],     # authoritative host projects
)

record = store.upload(
    **context,
    card_id="example-1",
    filename="document.pdf",
    content_base64=untrusted_base64_string,
    request_id="upload-operation-123",          # stable across retries
    now="2026-10-20T18:30:00Z",                 # HOST timestamp with timezone
)

listed = store.list_card(**context, card_id="example-1")
response = store.read(**context, attachment_id=record["id"])
preview = store.preview(**context, attachment_id=record["id"])
deleted = store.delete(**context, attachment_id=record["id"],
                       request_id="delete-operation-124", now="2026-10-20T18:35:00Z")
```

All command input arguments are keyword-only. `accounts` may be the current
LAN `{username: account}` mapping or a list of records with `username`,
`role`, `projects`. `cards` and `projects` may be a list of indexed records or
a mapping keyed by `id`. The host **must never trust client copies of these
inputs**. `AttachmentError` (a `ValueError`) indicates invalid input or
integrity/storage-path problems; `PermissionError` indicates forbidden access.
SQLite/OS storage failures propagate and must not be reported as success.

| Method | Permission | Response |
| --- | --- | --- |
| `upload(...)` | Authenticated admin/editor within card's project | Attachment metadata |
| `list_card(..., include_deleted=False)` | Authenticated scoped admin/editor/viewer | Ordered active attachment metadata |
| `list_card(..., include_deleted=True)` | Admin | Includes deleted tombstones |
| `read(..., attachment_id=...)` | Authenticated scoped admin/editor/viewer | Base64 contents plus safe download response metadata |
| `preview(..., attachment_id=...)` | Authenticated scoped admin/editor/viewer | Bounded passive preview descriptor |
| `delete(..., attachment_id=..., request_id=..., now=...)` | Admin or original uploader with current project edit rights | Deletion receipt; retains tombstone |
| `audit_log(..., project_id=...)` | Admin | Upload/delete events for one project |
| `backup_to(new_destination, *, actor, accounts)` | Admin | Complete manifest of the newly published backup |
| `AttachmentStore.verify_backup(source)` | Trusted host maintenance | Checked manifest of the supplied backup |
| `AttachmentStore.restore_backup(source, new_destination)` | Trusted host maintenance | New store; **never overwrites an existing destination** |

The host must restrict access to the restore/verify entry points to local
trusted maintenance code. These are intentionally not LAN user operations.

## Request and content limits

- Upload accepts one canonical, bare Base64 string only, containing at most
  **4 MiB (4,194,304 bytes) decoded content**. The matching maximum Base64
  input length is **5,592,408 ASCII characters**. No `data:` URLs, whitespace,
  noncanonical encoding, empty payloads, or invalid padding. Configure the
  HTTP endpoint body limit for this encoded size plus narrowly bounded JSON
  overhead, and enforce an application-level request rate/volume quota.
- Extensions: `.png`, `.jpg`, `.jpeg`, `.pdf`, `.txt` only. Content type is
  **detected server-side** from bytes and must agree with the extension.
  PNG requires a valid signature, IHDR, dimensions, CRC-checked chunks,
  IDAT and final IEND. JPEG checks the JPEG magic/terminator. PDF checks its
  version prefix and end marker. Text must be valid UTF-8 and excludes binary
  control codes and markup-looking HTML/SVG. Neither SVG nor HTML is an
  accepted file type.
- Filenames are single basenames, maximum 180 characters. Slashes,
  backslashes, drive specifiers, path traversal, Windows device names,
  control characters, bidirectional overrides and unsafe punctuation are
  rejected. Filenames never become filesystem paths. They are stored only
  as metadata. The host should also encode them safely in response headers
  when presenting a downloadable filename.
- Up to 100 **active** attachments can be associated with a card; tombstones
  are retained separately. Content-addressed SHA-256 blobs are reused between
  cards/uploads with identical bytes without conflating their metadata.

`read` returns:

```json
{
  "attachment": {
    "id": "att-...", "cardId": "example-1", "projectId": "p-sample",
    "filename": "document.pdf", "mime": "application/pdf",
    "size": 38288, "sha256": "...", "uploadedBy": "editor",
    "createdAt": "2026-10-20T18:30:00Z", "deletedAt": null
  },
  "contentBase64": "...",
  "contentType": "application/pdf",
  "contentDisposition": "attachment",
  "xContentTypeOptions": "nosniff",
  "cacheControl": "no-store"
}
```

Example values above illustrate the shape; they are **not** claims that such
an attachment exists in any user's project. For HTTP responses, the server
must set `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`
and `Cache-Control: no-store`; never render untrusted bytes as HTML. A JSON
response to LAN clients must also be served with `application/json` and
`nosniff`. The result deliberately contains no OS blob paths.

## Passive preview contract

`preview` returns `{attachment, available, kind, truncated, content}`.

- **TXT:** `kind="plain-text"`. `content` contains up to **64 KiB** of
  decoded text (possibly `truncated=True`). Render it with React text nodes
  or DOM `textContent`. Never use `innerHTML`, Markdown with raw HTML or
  `eval`. This module intentionally rejects HTML-like tags in uploads.
- **PNG/JPEG:** `kind="image"`. `content` is Base64 only if the entire image
  is no larger than **256 KiB**; otherwise `available=False` and no raw bytes
  are returned. Render as an image element with the declared MIME type,
  protected by a restrictive Content Security Policy.
- **PDF:** `kind="pdf-download-only"`, `available=False`, `content=None`.
  This is an intentionally passive PDF placeholder with filename/size; the
  bytes are available through the authorized **download** path. The module
  never embeds a PDF, executes JavaScript or invokes a third-party PDF
  rendering engine. A rendered first-page PDF thumbnail would require a
  separately sandboxed rasterization service and security tests.

The MIME sniffing here is a **bounded initial gate**, not an antivirus
scanner or a full forensic validator for JPEG/PDF internals. PDF documents
can contain active features; they are strictly download-only in this API.
Image decoding should remain in the browser's sandbox, with an appropriate
CSP and updates to WebView2.

## Data layout, atomicity, authorization

The host-selected storage root contains:

```text
attachments-root/
  attachments.sqlite3       # metadata, receipts, append-only audit rows
  blobs/
    2f/
      2f...(64-character SHA-256 digest)
```

The blob path is derived **only** from the validated digest, never an
original name or client-supplied path. Existing symbolic links and Windows
junctions in root, ancestors, blob directories/files, metadata and SQLite
sidecar paths are refused. Each newly written blob is flushed and `fsync`'d
to a temporary file in its shard and published with `os.replace`. Only
afterward is metadata inserted within `BEGIN IMMEDIATE` SQLite transaction,
with `synchronous=FULL`. If a crash occurs between blob publication and
the metadata commit, an unreferenced blob can remain; it cannot appear as
an active attachment. Such blobs should be collected only through a separate
reviewed garbage-collection step after backups, never during upload.

The database includes `attachments`, `audit`, `receipts` and `user_version=1`.
An existing SQLite database with an unsupported or unversioned schema is
rejected rather than silently migrated or populated with attachment tables.
Its schema is inspected through an explicitly closed read-only SQLite
connection before attempting any write transaction, so rejected databases
are not left locked on Windows.
Attachments are **tombstoned**, retaining digest and metadata. Audit rows
contain actor, card, project, operation, request ID and timestamp; read/list
never disclose rows of projects outside the current actor's scope. Restoring
an upload after deletion with the original request ID returns the original
recorded receipt; clients should refresh the active list to reflect the
current tombstone. Replay with changed content, actor or filename is rejected.

The manager has a thread lock and SQLite write transactions. Separate
processes using the same root are serialized for metadata writes by SQLite,
but the **host** must coordinate all changes to card project ownership and
permission grants. If a card moves to a different project, old attachment
records are inaccessible until an explicit authorized migration. This
prevents accidental cross-project attachment leakage. Local attackers with
write access to the store can race filesystem checks or replace blobs:
secure OS directory ACLs and avoiding attacker-controlled storage roots
remain required; no portable Python path check eliminates all TOCTOU races.

## Backup, verification and restore

`backup_to()` accepts an **absolute, not-yet-existing, disjoint directory**
whose parent already exists. It creates a SQLite online backup and copies
all referenced blobs, including tombstoned attachments, while checking
their lengths and SHA-256 digests. It writes `manifest.json` last and
atomically publishes the complete folder under the chosen name. Manifest:

```json
{
  "schemaVersion": 1,
  "databaseSha256": "64 lowercase hex digits",
  "blobs": [{"sha256": "64 lowercase hex digits", "size": 1234}]
}
```

`verify_backup()` hashes the database, checks `PRAGMA integrity_check`,
schema version and exact blob inventory, then reads each blob and compares
the recorded size and checksum. `restore_backup()` requires a **new empty
destination path** outside the backup source, verifies before copying, and
publishes through a fresh staging directory and atomic rename. Existing
destination data are never overwritten. The backup manifest is protected
against unintentional corruption using checksums, **not a signature**;
an attacker able to modify the whole backup can recalculate its hashes.

Host backup/restore integration must treat the SQLite file, all blobs,
manifest, project/card state and the separate LAN user-account store as a
**coherent backup set**. The current JSON-only and Drive snapshots do not
automatically include this new binary store. Before swapping a host or
restoring attachments, ensure referenced card IDs, project scopes and
account identities are restored from compatible versions and take a verified
safety backup. A restore into the currently active store is prohibited.

The code doesn't purge tombstones, handle malware detection, provide a
dedicated PDF rasterizer, encrypt blobs at rest or authenticate Google Drive.
The existing LAN transport still needs TLS before transfers on untrusted
networks. Test external NAS/SMB shares and multi-host failover separately.

## Integration steps

1. The Bridge owner constructs one store per authoritative host using a
   server-selected path under its application data folder. The module itself
   never chooses or opens APPDATA. The LAN host reuses this store; clients
   must not write directly to blob directories.
2. Add authenticated `upload/list/read/preview/delete` host calls. Resolve
   actor from the session token, and cards/projects/accounts from the latest
   authoritative host state. Bound JSON request size before parsing and
   preserve request ID through network retries.
3. Map `AttachmentError` to an appropriate request/integrity failure response,
   `PermissionError` to HTTP 403, and storage failures to error responses.
   Avoid leaking filesystem paths or stack traces. Check card ownership
   and deleted state on **every** read, list and delete.
4. Include blob backup export, manifest verification and safe restore in
   application backups. Keep legacy SMB `fileLinks` independent; they remain
   links to local network shares, not uploaded binary attachments.

To run isolated Windows tests:

```powershell
python -m unittest discover -s tests -p test_attachments.py -v
```

These tests use `tempfile.TemporaryDirectory` rather than the live Madar
application data. The test scope covers permissions, scope revocation,
deduplication, corrupted bytes, Base64 limits, active-content rejection,
bounded previews, safe paths, concurrent retries, tombstone audit and
backup/restore. Live LAN endpoints, real backups to Drive, PDF thumbnail
rasterization and physical multi-PC access are outside this module's tests.
