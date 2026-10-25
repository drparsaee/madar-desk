# Madar Desk 1.0 — Safe Portable Windows EXE Installer

## What this is

An **explicitly user-invoked**, PowerShell 5.1-compatible, **portable EXE install/update script**:

- Script: \`scripts/Install-MadarDesk.ps1\`
- Test suite: \`tests/test_portable_installer.py\`
- Destination EXE name: **\`Madar-Desk.exe\`**
- Required arguments: **\`-SourceExe\`** (existing local Windows EXE), **\`-InstallDir\`** (explicit ordinary local absolute path)

It is **not** an MSI/MSIX installer or auto-updater. It installs one Windows EXE only. It does **not** run the EXE, migrate application state, touch APPDATA, create shortcuts, change registry, add Windows services, change Task Scheduler/startup, download packages, request elevation, or contact the network.

**Important coexistence note:** Prime has separately prepared \`release/Install-Madar-Desk-v1.0-rc1.ps1\` with its own release smoke tests. This worker did **not** modify or replace that separate release artifact. The present script is a hardened reusable updater for explicit future invocation. Prime decides whether and how to ship it.

## Exact manual command

In **ordinary, non-administrator PowerShell**, choose an installation folder you own. Close any installed \`Madar-Desk.exe\` instance first:

\`\`\`powershell
powershell.exe -NoProfile -File "D:\CoS-Test\madar-desk\scripts\Install-MadarDesk.ps1" -SourceExe "D:\CoS-Test\madar-desk\release\Madar-Desk-v1.0-rc1.exe" -InstallDir "D:\Apps\MadarDesk"
\`\`\`

**Recommended provenance check:** obtain the independently trusted SHA-256 digest from the release publisher or an authenticated release manifest. Then supply it explicitly:

\`\`\`powershell
powershell.exe -NoProfile -File "D:\CoS-Test\madar-desk\scripts\Install-MadarDesk.ps1" -SourceExe "D:\CoS-Test\madar-desk\release\Madar-Desk-v1.0-rc1.exe" -InstallDir "D:\Apps\MadarDesk" -ExpectedSha256 "<64-hex-digits-from-a-trusted-release-record>"
\`\`\`

The \`<64-hex-digits-from-a-trusted-release-record>\` placeholder must be replaced; it is not a real digest. A SHA-256 computed from an untrusted download itself does **not** authenticate that download. The PE check verifies basic binary *structure*, not an Authenticode signature, publisher identity, or the safety of its executable code.

Do not run as administrator; the script does not elevate privileges. If PowerShell script execution is blocked by machine policy, ask the responsible administrator to sign/approve the script rather than weakening organization policy. The suite uses \`-ExecutionPolicy Bypass\` **only** in isolated test subprocesses; the normal user instructions above do not override policy.

## Safety / data preservation contract

1. **Before installation:** confirms both arguments are absolute drive-letter paths, that source is an existing \`.exe\` outside the installation folder, rejects drive roots, UNC/device paths, symlinks and junctions on path ancestors, and rejects installation inside Windows/Program Files/ProgramData/APPDATA/LOCALAPPDATA trees.
2. **PE preflight:** opens the candidate for read-only inspection; checks DOS \`MZ\`, the PE offset/signature, COFF architecture and section count, bounded optional header, PE32/PE32+ magic and section-table bounds. The same checks run again after staging.
3. **SHA-256:** hashes the original and the staged copy and requires equality. If \`-ExpectedSha256\` is supplied, requires it to match **before creating the install directory**.
4. **Exclusive updater lock:** creates \`<InstallDir>\.madar-portable-install.lock\` with \`FileMode.CreateNew\` and \`FileShare.None\`; refuses an existing/stale lock without modifying or removing it. Lock is removed only by its creator during ordinary process cleanup.
5. **Running/locked app refusal:** checks named \`Madar-Desk\` processes and their EXE paths; refuses unknown running paths. Attempts an exclusive handle on an existing target before copying and again before backing it up. Refuses an existing non-PE target and never overwrites unrelated files.
6. **Stage first:** copies the source to a **uniquely named same-directory** \`.Madar-Desk.stage.<UUID>.exe\`; validates PE/header and hash. The old target remains active until staging has finished.
7. **Unique backup:** if an old target exists, moves it to \`Madar-Desk.backup.<UTC-timestamp>.<UUID>.exe\` in the same directory, then atomically renames staged EXE to the fixed installed name. Older backups and other \`release\` artifacts are never purged or overwritten.
8. **Rollback:** if the operation fails after backup, restores the old EXE byte-for-byte by moving its backup back. If the new EXE was already renamed, it is preserved under unique \`Madar-Desk.failed.<UUID>.exe\` first. Failed first-time installs do not leave an unverified installed EXE. An unremovable/locked old backup is preserved and a manual recovery error explicitly shows its location.
9. **Identical hash:** reapplying the same valid EXE is a no-op with no additional backup.
10. **No user-state access:** no code opens, changes or removes \`tasks.json\`, SQLite files, application preferences, caches, user profiles, stored credentials, or any other APPDATA artifact. Tests place explicit sentinel user-data files in **synthetic APPDATA**, verifying they remain unchanged.

### Files created inside InstallDir

| File | Purpose / retention |
| --- | --- |
| \`Madar-Desk.exe\` | Only installed binary and only fixed filename that can be replaced |
| \`Madar-Desk.backup.<time>.<uuid>.exe\` | Unique previous binary retained on successful upgrade |
| \`.Madar-Desk.stage.<uuid>.exe\` | Temporary full copy; removed or renamed during ordinary cleanup |
| \`.madar-portable-install.lock\` | Exclusive updater lock; removed after normal completion/failure, **not** if it already existed |
| \`Madar-Desk.failed.<uuid>.exe\` | Preserved new binary if failure happens after new rename, for diagnostics |

The source release EXE stays untouched. Existing installer backups and other release files are not overwritten.

## Tests and evidence

Run on Windows PowerShell 5.1 with Python 3.12:

\`\`\`powershell
cd "D:\CoS-Test\madar-desk"
py -3.12 -m unittest tests.test_portable_installer -v
py -3.12 -m unittest tests.test_release_portable_install -q
\`\`\`

**Observed results:** own portable updater **17/17 PASS** (final rerun: 13.000 s); Prime's separate release portable installer regression **1/1 PASS** (2.683 s). Coverage includes:

- New installation, updates from multiple synthetic PE revisions, unique old-binary backups and preservation of unrelated release files
- Matching/mismatching trusted digest, invalid header/extensions, existing non-PE target and protected directory refusal
- Existing/stale updater lock and a deliberately non-shareable open Windows target file refusal
- Failure injection **after old-target backup**, plus **after final target rename**, on first install and upgrade; restore/retention assertions
- Idempotent reinstallation of unchanged binary without new backups
- Source located inside destination, drive root, UNC and relative path refusals
- Actual \`release/Madar-Desk-v1.0-rc1.exe\` (when available) installed **only to temporary destination** with its SHA-256 checked; original RC artifact is read-only and never replaced
- Synthetic APPDATA database sentinel unchanged in every scenario

The test's **explicit fault-injection-only** switches \`-TestFailAfterBackup\` and \`-TestFailAfterRename\` intentionally cause an error and rollback. Never pass these to a real installation.

Every case operates beneath a new disposable project-local directory created by Python \`TemporaryDirectory\` and removes it after the test. Tests do not use production APPDATA, the configured real installation directory, existing release targets or an actual running executable process.

## Limits / operational caveats

- **Portable EXE only.** If an RC build requires neighboring DLLs, assets or external files instead of embedding them, those dependencies are **not** installed. Verify release packaging independently.
- The basic PE parser is a corruption/type guard, **not** full Windows loader validation, a malware scanner, Authenticode verification, or executable provenance. Use an independently trusted SHA-256 and Windows signature checks where your release process requires them.
- Each rename within one local directory is atomic on a typical local Windows filesystem, **not** the combined backup-and-replace sequence. Unexpected power loss/process termination between renames may leave a uniquely named backup and no target; recover manually from that backup. An abandoned lock also intentionally causes conservative refusal; investigate and remove the stale lock manually only after confirming no installer is active.
- There remains an unavoidable small race between a final running-process check and the rename. Windows file sharing protections offer further refusal; this is not a guarantee against a malicious local concurrent process.
- The script does not stop or kill any process. A real app-in-use test is represented by a nonshareable handle on a disposable PE file; it does **not** claim a production EXE was executed or tested while running.
- It does not require, request, or validate administrator privileges. Installing in paths where the account lacks normal write access safely fails.
- No automatic rollback across later launches, automatic integrity monitoring, update catalog, GUI prompt, network fetch, shortcut, uninstaller, or scheduled run is provided.
- This script has **not** been substituted for Prime's existing RC release-install script; use the release owner's final packaging decision.
