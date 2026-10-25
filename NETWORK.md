# Madar local network mode (v0.5 release candidate)

## HTTPS (recommended for new networks)

On the host, generate a unique TLS certificate/private-key pair (instructions
in `LAN_TLS.md`) and secure the private key on that computer. In the LAN dialog
select HTTPS, enter both local PEM paths and start the host. The host displays
the SHA-256 certificate fingerprint. Compare that full fingerprint with the
one entered into every client using a trusted separate channel. Clients use
`https://PRIVATE-IP:PORT` and reject a missing or mismatched fingerprint
before sending passwords or tokens. Reissuing the certificate requires clients
to verify its replacement fingerprint explicitly; no silent HTTP fallback.

The older HTTP path remains available for compatibility, clearly labeled as
unencrypted. HTTPS is implemented and tested locally but **has not yet passed
the physical two-Windows-PC acceptance gate**.

## On the server computer

1. Start Madar Desk, open **شبکه محلی و کاربران**.
2. Choose **فعال‌کردن سرور محلی**, enter an English owner username, a strong password (minimum 10 characters) and port (default 48370).
3. Find the LAN IPv4 address of that computer (PowerShell: `ipconfig`). The URL will look like `http://192.168.1.20:48370`.
4. Allow this port **only on Windows Firewall Private profile and only for your trusted LAN subnet**. Do not forward this port on the router or expose it on the Internet.
5. Open **مدیریت کاربران**. Create colleagues with role **Admin**, **Editor**, or **Viewer** and grant the allowed projects or all projects.
6. Keep the program running on this PC. The host owns the authoritative local
   state (`tasks.json` in legacy mode or `madar-unified.sqlite3` after explicit
   opt-in migration). Never sync the active SQLite file through a shared drive.

## On a second computer

1. Run a copy of the same EXE. Open **شبکه محلی و کاربران**, enter the host's LAN URL and your own account credentials.
2. The client reads and writes through an authenticated LAN API rather than sharing the JSON database folder.
3. Connected clients poll about every 3 seconds and see saved changes.
4. **Viewer:** read only; **Editor:** task modifications within authorized projects, no project or global settings edits; **Admin:** management including user accounts.

## Sync and security constraints

- An edit includes the revision of the state it was based on. If another client saved a newer revision, the server refuses the stale edit (HTTP 409); it never silently replaces another user's changes. The client displays the error and holds a recovery copy in its local WebView storage. Resolve the conflict and refresh.
- Password hashes use PBKDF2-HMAC-SHA256 with a random per-user salt. Session tokens expire after 12 hours. The client's remembered password is encrypted with Windows DPAPI. Credentials and permissions stay separate from Drive backups.
- **Important:** HTTP connections remain unencrypted. Use HTTPS with a verified
  certificate fingerprint for credentials and sensitive task information. Do
  not expose either service to the public Internet or port-forward it.
- The host must stay on. LAN synchronization is near-real-time polling, not offline edits that later merge. Closing the host interrupts client access. No automatic conflict merge.
- For Google Drive data transfers, make backups on the host, not on a client. Google Drive remains separate from LAN collaboration.
