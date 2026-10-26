# Madar Accounting R13 | Security P0 candidate and tax preflight

**Date:** 2026-10-26. **Status:** installed side-by-side, synthetic-tested.
**Not** production-certified or approved for genuine taxpayer transmission.

## Scope completed

### Local company identity and least privilege
- Each company has an independent `local-users.json` (no shared password DB).
- First new company requires an administrator-created username/password of at
  least 12 characters, with no default credential supplied.
- Password verifiers are PBKDF2-HMAC-SHA256 with 600,000 iterations and random
  salts; no plaintext password is written to company data or JavaScript.
- Windows-native branded login is displayed **before** the accounting WebView
  and ledger are initialized.
- User roles: `admin`, `editor`, `viewer`. Direct financial mutations are
  authorized by the server-side `accounting_core` role rules, not by hidden UI.
- Session tokens are held only by the Python host, never passed to a JavaScript
  request. Reads, commands, templates, switching and tax preflight re-check
  authentication. Explicit logout/expiration denies the next operation.
- Administrators can create, disable, change roles and reset other account
  passwords using the native user-management dialog. A user cannot downgrade
  or disable their own final administrator account.
- Failed-login rate limits are tracked in the identity registry for known
  accounts and in process memory for unknown accounts.
- Existing financial books missing their user registry are rejected in the
  secured company launcher, instead of implicitly creating a new admin.
- Managed company folders still use the session lock, even if opened via an
  explicit data-directory option.

### Identity backups and restore
- A verified accounting snapshot now has an independent `.users.json`
  companion when company identities exist. The companion stores verifiers,
  **not** plaintext passwords. Template companions are preserved.
- The offline restore checks account schema, denies pre-existing targets and
  restores the SQLite book and user registry together, rolling back its own
  publications on failure.
- Existing legacy backups without user companions remain legacy; they do
  **not** recreate missing user identities.

### Tax advisory preparation
- `standalone_accounting_tax_advisor.py` provides a **read-only, offline**
  pre-submission checklist identifying missing taxpayer identifiers,
  goods/services mapping, referenced amendment/cancellation documents and
  invalid line quantities/prices.
- The invoice list includes a preliminary advisory action with a visible
  issues list. It never signs, transmits or posts a financial record.
- Two historic technical/regulatory references are identified by document
  name/version, explicitly marked **not verified as current**.
- No percentage/rate is invented, and `readyForSubmission` is always false
  pending a verified current rule pack and authorized signing workflow.
- This is **not yet an LLM-based legal advisor** and is **not connected to
  سامانه مؤدیان**. Those are F1 backlog deliverables.

## Git and further modules

- Dedicated local Gitea responds on http://127.0.0.1:3000/; SSH is disabled.
- An independent initial Madar bare Git snapshot exists in
  `C:\APPS\LocalForge\migration-staging\madar-desk.git`; its local integrity
  was checked separately. It has **not** been verified as a Gitea-hosted remote
  repository. No push, remote association or claim of synchronization occurred.
- The source workspace `D:\CoS-Test\madar-desk` remains independent of Git
  metadata. Never imply its current R13 state is committed.
- All other gaps and acceptance criteria are enumerated in
  `MADAR_CAPABILITY_BACKLOG_20261026.md`, phases F0 through F8:
  F1 Modian/tax, F2 inventory, F3 print production, F4 payroll, F5 fixed
  assets, F6 CRM, F7 secure APIs/n8n and F8 final acceptance.

## Evidential tests

- Native Tk premium first-admin bootstrap, rejection and cancel flow: 3 PASS.
- Accounting identity roles/session isolation and backup/restore companions
  were tested on disposable folders.
- Real R13 one-file EXE synthetic end-to-end:
  **13/13 PASS** (premium chooser, password login, SQLite initialization,
  startup and mandatory exit backups, replay validation, identity companion
  and login after offline restore).
- R13 installed executable SHA-256 matches release SHA-256.
- R13 installed chooser cancel: **6/6 PASS** and no unwanted ledger.
- The immediate predecessor R12 release hash is unchanged.
- JavaScript suite: **372/372 PASS**.
- Final targeted Python suite rerun after the identity/backup changes:
  **110 tests, OK (expected failures=2)**. Those two expected failures are the
  documented direct-Python/legacy access threat contracts, not passed
  security controls.

## Artifact

- Release file: `release/Madar-Accounting-Secure-Tax-R13-20261026.exe`
- Size: **16,795,520 bytes**.
- SHA-256:
  `5C4AE111DC8370163D85428B127AA49BEAAC777625B99F1452BDA2D7B03F88B0`
- Installed to
  `%LOCALAPPDATA%\Programs\Madar Accounting Mohsen R13`.
- Separate company hub:
  `%LOCALAPPDATA%\Madar Accounting Companies R13`.
- Desktop shortcut: `Madar Accounting R13 - MultiCompany.lnk`.

## Unresolved, explicitly out of production acceptance

1. Local OS users with unrestricted file access can still read/copy unencrypted
   SQLite and password-verifier backups. Windows ACL enforcement and encrypted
   backup/restore with key recovery are not implemented.
2. A skilled local user running arbitrary Python against raw SQLite can bypass
   application-level roles. Application authentication is not full-at-rest
   encryption. Legacy explicit `--data-dir` and old releases remain available.
3. Complete LAN/multi-machine authentication, mandatory MFA, administrator
   recovery, password rotation policy, audited session management and
   penetration testing are outstanding.
4. Existing R12 company books without an identity registry need controlled
   migration; R13 does not guess or silently convert credentials.
5. No official current-year tax rule pack, officially permitted signing
   credentials, real tax submission, sandbox acceptance or tax-adviser
   professional sign-off has been validated.
6. Production backup encryption, recovery of user accounts after lost passwords
   and real fiscal testing must be completed before financial go-live.

**R13 is a materially improved secured local candidate, not a complete
multi-user or statutory-compliant accounting release.**
