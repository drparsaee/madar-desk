# Madar Accounting R18 | User Roles and Latest Parsian Backup Trial

**Date:** 2026-10-26  
**Scope:** new side-by-side Madar R18 plus one private, isolated migration experiment.  
**No production Parsian database or previous R15/R16 book was modified.**

## User management

- New per-company account form: Latin username; editable Persian job title with presets (مدیر ارشد، مدیر مالی، حسابدار، کارمند، سرپرست، مسئول فروش، مسئول انبار); independent permission mapping (`admin`, `editor`, `viewer`). A self-declared job title **never grants permissions**.
- Job title displayed directly beside username in the top bar after authentication and in the user management table; existing `local-users.json` records without `jobTitle` remain compatible.
- Password policy changed from minimum 12 characters to **minimum 4 characters**; four-digit numeric PINs work. Longer strings remain accepted, with no password stored in plain text in the identity JSON. Passwords are hashed using the pre-existing PBKDF2-HMAC-SHA256 verifier. Lockouts and server-enforced roles remain.
- 4-digit numeric PINs are significantly easier to guess than longer passwords. This is an owner-requested convenience setting, not a recommendation for high-risk production credentials.
- Native user manager provides create, edit title/permissions, password reset and disable; admin-only backend checks remain.

## Source backup selected

- Original: `C:\BACKPARS\db_1405.BAK` (2026-10-26 15:15, 6,375,936 bytes).
- Different from the 15:00 original `C:\Program Files (x86)\Parsian\db_1405.bak` (SHA differs). No source file was overwritten.
- Exact independent copy: `D:\CoS-Test\madar-desk\.private-parsian-staging-20261026\parsian-latest-20261026-1515.bak`, marked read-only.
- SHA-256 of owned copy and source: `65E85D8BED539C4CB98D2A3F20416637524E5133CB7B940D6A4015A7CA368441`.
- SQL Server 2000 8.00.194: RESTORE HEADERONLY, FILELISTONLY and VERIFYONLY passed. BackupType=1 (full), source database name `db_1405`; logical files `db_13851_Data`, `db_13851_Log`.
- Database **restored under the distinct QA name** `MadarR17ParsianQA20261026`, physical files inside `.private-parsian-staging-20261026\restored-sql-r17`. Existing `db_1405` was not restored over or altered. The temporary QA database remains for audit. It shares the SQL Server instance, so this is not a separate SQL Server installation.

## What the restored backup actually contained

| Measurement | Restored 15:15 backup |
| --- | ---: |
| Vendor `tbl_*` tables | 98 |
| All archived source rows | 10,135 |
| `tbl_Document` source rows | 256 |
| Balanced journal groups | 124 |
| `tbl_Factor` rows | 142 |
| `tbl_Goods` rows | 95 |
| `tbl_Check` rows | 0 |
| `tbl_Kol` / `tbl_Moeen` / `tbl_Tafsili` rows | 24 / 62 / 49 |
| Parsed unique Persian source dates | 61 |

- 124/124 source journal groups balanced, zero orphan `Kol/Moeen/Tafsili` references and no oversized/singleton journal groups.
- 2 source factor rows have journal numbers absent from extracted journal groups; this needs business mapping review, not guessed journal creation.
- 2 `Kol.GroupCode` values have no matching `tbl_ACCGroup` reference; review required.
- Data from restored QA SQL, **not an assumed equivalent live SQL database**, was exported and quarantined before any Madar posting.

### Comparison with the previous 2026-10-24 trial export

The previous trial (`.private-parsian-staging-20261024/.../gl-import-audit.json`) reported 116 journal groups, 240 journal lines and 44,776,829,000 RIAL on each debit/credit side. The newly restored 15:15 backup has 124 groups, 256 lines and 46,033,769,000 RIAL per side: **+8 groups, +16 lines and +1,256,940,000 RIAL on each side**. In both trials 88 catalog goods qualified for import. Crucially, the earlier source was an attached-live SQL export, whereas the new source was restored from the specific 15:15 BAK. These differences are observations, **not** a proven accounting change history or evidence of when/why the source data changed.

## What entered the disposable Madar trial

Source: `D:\CoS-Test\madar-desk\.private-parsian-staging-20261026\migration-experiment-20261026\`

Within `parsian-rial-gl-import-disposable`:

- 124 legacy journal groups posted as trial `journal.manual` entries, 256 balanced lines, 37 referenced legacy chart accounts, 88 goods with confirmed nonempty unit, 7 unit-missing goods deferred; RIAL persisted.
- Debit and credit totals both **46,033,769,000 RIAL**. These source totals equal those imported into Madar; per-account movement comparison and SQLite replay checks passed. Revision of trial book after import: **249**.
- Lossless raw quarantine and full 98-table historical source archive with `PRAGMA integrity_check=ok`; metadata identifies the actual isolated restored BAK source and SHA.
- Historical view: **66 grouped historical factor documents**, **7 positive-balance historical debtor accounts**. They remain archival references, not operational invoices or new receivables posted again.
- No modern sales/purchase invoices, cheques, stock movement, receipt, payment, or normalized party subledger was fabricated from unresolved legacy rows. Sales KPI based on issued *new* invoices can therefore be zero despite historical GL revenue; the historical archive and GL reports should be used to inspect legacy amounts.
- This trial is **NOT** an approved production migration, full accounting equivalence or substitute for Parsian. Some account classifications are provisional. Even with original BAK snapshot provenance confirmed, the financial unit/mapping/party opening balances need human reconciliation before any live adoption.

## Test sign-in and access

- The disposable test book has an authenticated *new* local user `trialadmin`, display title `مدیر ارشد`, security role `admin`. Its password is randomly generated and stored only here, with private ACLs:
  `D:\CoS-Test\madar-desk\.private-parsian-staging-20261026\migration-experiment-20261026\R17-TRIAL-LOGIN-PRIVATE.txt`
- The private experiment root ACL was restricted to the current Windows owner, SYSTEM and Administrators (no inherited Authenticated Users/Users access).
- Desktop direct shortcut: `Madar R18 - Parsian Latest Trial.lnk` opens this exact test book with `--data-dir`. `Madar Accounting R18 - MultiCompany.lnk` opens a **separate fresh, empty** R18 company registry, not the historical trial.
- The R18 trial was launched for the user in the current Windows session; a separate process and an owned visible native secure-login window were observed. This is not confirmation that the user entered the generated password.
- After first sign-in, use **کاربران → بازنشانی رمز** to replace the generated trial password if desired.

## Verification performed

| Check | Result |
| --- | --- |
| R18 production Vite build | PASS, 1,673 modules |
| All JS suite `node --test tests/*.test.cjs` | **388 PASS, 0 FAIL** |
| Targeted Python identity/legacy backup test suite | **39 PASS, 0 FAIL** |
| Focused new identity policy suite | Included; 4-digit PIN, typed title, ACL unaffected, backup compatibility and host user projection tested |
| Real native WebView on restored-BAK test book | **13 PASS, 0 FAIL** (title next to username, historical archive navigation, dashboard, no changed revision) |
| Packaged R18 EXE with synthetic disposable data | **8 PASS, 0 FAIL** (window, SQLite, startup/exit backup, backup integrity, normal close) |
| Installed R18 EXE against imported trial | **9 PASS, 0 FAIL** (password gate opened, no unauthenticated ledger window, clean close and unchanged revision) |
| Complete packaged login with typed password | **NOT TESTED**: no automated credential injection/focus guarantee; native Python-authenticated host and the login gate were tested separately |
| Final unobstructed visual snapshot of user-management dialog | **NOT VERIFIED**; underlying role/title API and WebView title were verified |
| Full real-world end-user financial comparison against Parsian reports | **NOT VERIFIED**; conservative archival and GL-only trial as above |
| Git/Gitea push | **NOT PERFORMED**, workspace had no `.git` during prior checks |

## R18 release and installed files

`D:\CoS-Test\madar-desk\release\Madar-Accounting-User-Roles-Parsian-Trial-R18-20261026.exe`

- File size: **16,816,198 bytes**.
- SHA-256 (release and installed file matched): `FF31DDD0DBD5B614E3F604BD9D0E04C15AB2DA90A3FE13DBE9B2E7AEC384F6ED`.
- Installed: `%LOCALAPPDATA%\Programs\Madar Accounting Mohsen R18`.
- New empty R18 company hub: `%LOCALAPPDATA%\Madar Accounting Companies R18`.
- Earlier R15/R16 release hashes remained unchanged. R17 was an intermediate candidate from the same task; use the corrected R18 build for user/title display.

**Scope statement:** This acceptance is a successful isolated restore, source archival preservation and partial GL import with operational accounting intentionally gated, not a claim that all Parsian rows were converted into live Madar transactional entities.
