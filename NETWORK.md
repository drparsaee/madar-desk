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
3. Find the LAN IPv4 address of that computer (PowerShell: `ipconfig`). For the recommended HTTPS transport, the URL looks like `https://192.168.1.20:48370` and clients must verify the complete certificate fingerprint. The legacy HTTP transport is unencrypted.
4. Allow this port **only on Windows Firewall Private profile and only for your trusted LAN subnet**. Do not forward this port on the router or expose it on the Internet.
5. Open **مدیریت کاربران**. Create colleagues with role **Admin**, **Editor**, or **Viewer** and grant the allowed projects or all projects.
6. In legacy GUI-host mode, keep the program running on this PC. Alternatively use the separately provisioned background Windows service described below. The host owns the authoritative local
   state (`tasks.json` in legacy mode or `madar-unified.sqlite3` after explicit
   opt-in migration). Never sync the active SQLite file through a shared drive.

## On a second computer

1. Run a copy of the same EXE. Open **شبکه محلی و کاربران**, enter the host's LAN URL and your own account credentials.
2. The client reads and writes through an authenticated LAN API rather than sharing the JSON database folder.
3. Connected desktop clients check for saved changes on the UI refresh cycle (currently 15 seconds), and may refresh explicitly. This is polling, not push.
4. **Viewer:** read only; **Editor:** task modifications within authorized projects, no project or global settings edits; **Admin:** management including user accounts.

## Sync and security constraints

- An edit includes the revision of the state it was based on. If another client saved a newer revision, the server refuses the stale edit (HTTP 409); it never silently replaces another user's changes. The client displays the error and holds a recovery copy in its local WebView storage. Resolve the conflict and refresh.
- Password hashes use PBKDF2-HMAC-SHA256 with a random per-user salt. Session tokens expire after 12 hours. The client's remembered password is encrypted with Windows DPAPI. Credentials and permissions stay separate from Drive backups.
- **Important:** HTTP connections remain unencrypted. Use HTTPS with a verified
  certificate fingerprint for credentials and sensitive task information. Do
  not expose either service to the public Internet or port-forward it.
- The host computer and its LAN listener must stay on. In GUI-host mode, closing the desktop window stops that listener; when the optional Windows service is installed and running on its separate data authority, GUI closure does not stop it. Offline edits may be queued but are not acknowledged by the host until successfully reconciled; conflicting edits are not silently merged.
- For Google Drive data transfers, make backups on the host, not on a client. Google Drive remains separate from LAN collaboration.

## Optional background Windows service / LAN discovery

See `HOST_SERVICE_SETUP_FA.md` for the opt-in `MadarHost.exe` service and its dedicated `ProgramData` data authority. Its HTTPS LAN listener can run while the GUI is closed. The service does **not** automatically adopt the GUI user's existing `%APPDATA%\MadarDesk` tasks, attachments, finance or accounts; users must not confuse a fresh service host with their previous data authority. No actual installation or two-physical-PC acceptance is implied by the source tests.

Configured HTTPS hosts may advertise an **untrusted** discovery hint on UDP 48371/48372 (`LAN_DISCOVERY.md`). The GUI simplifies finding a host, but a user must independently confirm the full TLS fingerprint before authenticated login; never trust UDP-supplied fingerprints as pinned keys. The host-only 30-second backup scheduler captures changed task/unified database revisions, with explicitly partial scope.
