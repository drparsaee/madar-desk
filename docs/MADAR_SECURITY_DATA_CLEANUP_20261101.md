# Madar Desk | Security, preservation, installation and cleanup

Date: 2026-11-01. Scope: Windows user profile and the private LocalForge
checkout for Madar Desk. This is a scoped engineering audit, **not a complete
penetration-test certificate**.

## Verified current installation

- Installed Madar Desk 1.0.2 with Inno Setup, actual installer exit code 0.
- Current version 1.0.2, installed EXE SHA256
  B33DA7B33EBD761BCC381DD22DE49FA0AD071EE11FE0AD133D9C77CAA1917405.
- All 82 user-profile files were hash-identical before and after the upgrade:
  zero modified, zero removed, zero added.
- A byte-exact copy of the installed executable passed fresh-profile QA
  and isolated interactive GUI smoke, including accounting navigation and
  creation of one synthetic task. Real accounting writes were not tested.

## Backup and cleanup

- The primary real-profile ZIP has 82 files, individually checked during
  backup. An independent test restoration confirmed the task JSON and
  SQLite PRAGMA quick_check=ok.
- Separate historical accounting data: 14 LocalAppData roots, 115 files.
  Archive: Madar-Legacy-Accounting-Profiles-20261101.zip; checksums verified.
- Old program recovery: 15 historic accounting/suite install folders,
  17 executable/helper files; hashes verified in
  Madar-Legacy-Installed-Binaries-20261101.zip before cleanup.
- Removed 128 obsolete/duplicate EXE and ZIP release packages with original
  total size 4,638,113,055 bytes, plus 10 obsolete checksum text files.
- Removed 15 old accounting/suite installation directories, old installed
  1.0.1 binary, 15 outdated Start Menu folders and duplicate garbled shortcut.
- Preserved the installed 1.0.2 version, its installer/build files, all
  original user-profile data, legacy accounting data roots and recovery ZIPs.
- Preserved unrelated research, staging, and non-Madar files.

## Security evidence

| Area | Result |
| --- | --- |
| Selected LAN/TLS/ACL/finance/recovery tests | 108 PASS, 2 expected failures |
| LAN test fixtures after removal of customer demo data | 28 PASS |
| npm audit with updated lockfile | zero reported vulnerabilities |
| Tracked-file and preliminary secret-pattern scan | 881 tracked files, 316 source files scanned, zero flagged |
| Actual installer preservation of user data | 82/82 SHA256 parity |
| Windows distribution signature | NotSigned |

## Open security risks and incomplete checks

1. **HIGH LAN concern:** native_app.py permits LanService to run without
   TLS certificates, while LanService defaults to binding to 0.0.0.0.
   Login credentials and bearer tokens may traverse private LAN HTTP
   unencrypted. Do not enable shared LAN access without valid TLS and
   certificate pinning. Enforce fail-closed TLS on non-loopback in a future
   release; it has not been implemented or tested by this operation.
2. **Code signing deferred:** 1.0.2 EXE and Inno Setup are unsigned.
   SmartScreen warnings may remain; Authenticode trust is not verified.
3. **Backup encryption:** recovery ZIPs are not encrypted at rest.
   Protect using Windows account permissions and trusted storage; do not
   store user records or live credentials in source Git.
4. **Testing limitations:** no full manual penetration test, Windows 11
   clean image, WebView2-absent machine, MITM exercise, exhaustive Python
   dependency audit, historical Git secret scan, or independent complete
   Parsian financial reconciliation was performed.

## Git boundary

Source, build scripts, tests and original user-owned design material belong
in the canonical private LocalForge main repository. External Trello page
extractions and fonts are reference material, not cleared for redistribution.
SQLite/JSON accounting or task profiles, credentials, and recovery archives
are private runtime data and are not safe to push in raw form to Git.
Source push is not complete until server authentication and readback succeed.
