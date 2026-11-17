# MTR E7: release-candidate packaging preflight (READ-ONLY, 2026-11-10)

**Decision: NO-GO for building or distributing from the currently shared
isolated Madar worktree. Conditional GO for an *offline build-only RC staging*
in a separate disposable, clean Windows build environment after the gates
below; never for installation, production distribution or E7 acceptance.**

This is source/metadata inspection and a read-only unit preflight, NOT a build,
installer QA execution, physical WebView2 acceptance, release signature,
service migration, customer-data test or publication. No installer, app,
WebView2 runtime installation, LAN service, user profile, external network,
packager or cleaner was started. No commit/push/deploy was performed.

## Observed snapshot

- **Source:** `D:\CoS-Test\000- Madar\madar-p2-gantt-notifications-20261107`,
  branch `feat/madar-p2-gantt-notifications-20261107`, HEAD
  `32bd8ffe5ebbb0f4cd5c011c59323ed32f8647ac`. This shared checkout
  contains tracked modifications and numerous untracked E0–E7 source/tests/docs
  owned by other agents. `git status --porcelain=v1 --untracked-files=normal`
  is **nonempty**. This audit did not change their work.
- **Static version identity: PASS.** `package.json.version`,
  `package-lock.json.version`, `package-lock.json.packages[""].version`,
  `madar_update.CURRENT_VERSION` and the v123 integrated wrapper agree on
  `1.0.23`. This does not establish which version is installed or that any
  untracked E0–E7 development has entered a committed release source.
- **Declared invocation:** `package.json:9-12`: `npm run build` runs
  `scripts/sync_font.py` and Vite; `npm run dist` aliases `dist:rc`;
  `dist:rc` calls
  `python -B scripts/build_integrated_v123.py --webview2 release/.madar-inno-prereq/MicrosoftEdgeWebView2RuntimeInstallerX64.exe`.
  The wrapper passes this argument through to the imported base builder.
- **Disk presence (read-only `Get-Item`/directory listing):** `dist/` and
  `node_modules/` exist (no dependency-tree verification or built-asset
  provenance); `assets/madar.ico` exists. `release/`, the embedded offline
  WebView2 prerequisite, the expected 1.0.23 EXE/installers/manifest,
  `.qa-inno-v123-integrated/` and `.qa-p0-pyinstaller/` were **absent** at
  inspection. No installed Inno compiler/Python tooling was queried through
  a real user profile, so its availability is **unknown**.
- **Direct check:** `py -3.12 -B -m unittest -v
  tests.test_mtr_package_preflight_20261110` yielded **4/4 PASS, exit 0**.
  The test prints:
  `dirty_or_untracked=true`,
  `webview2_offline_prereq_present=false`,
  `release_artifact_collision=false`,
  `dist_present_not_attested=true`,
  `current_builder_source_gates_pass=false`.
  It parses/reads source, JSON and Git status only; it never imports/calls the
  builder or invokes an installer. It does **not** validate the absent
  prerequisite's signature or any toolchain/compiler availability.

## Execution and side-effect map: *do not invoke during this audit*

| Step | Source evidence | Side effects / safety disposition |
|---|---|---|
| Version and immutability gate | `scripts/build_integrated_v123.py:39-57,170-180` | Checks package/lock/updater `1.0.23`, exact output names, existing artifacts and then **requires a fully clean Git status**, including untracked files. Shared worktree fails. `git status` itself is read-only. |
| Base builder imports/argument | `build_integrated_v123.py:17-30,181`; `build_p0_release_candidate.py:62-73` | Wrapper rebinds base v1.0.3 defaults to 1.0.23; never run base builder directly. Base requires `--webview2`, Inno compiler at `Path.home()/AppData/Local/Programs/Inno Setup 6/ISCC.exe`, existing offline prerequisite, no artifact collision, then Microsoft Authenticode signature. Prerequisite absent here. |
| Offline prerequisite | `build_p0_release_candidate.py:33-40,69-80`; `madar-update.iss:85-87,120-183` | Creates `release/.madar-inno-prereq/`; may copy signed input, hashes and embeds it in the **non-compact** setup. Signature verification proves a Microsoft-signed file, **not by itself that it is the full offline x64 runtime rather than a signed bootstrapper**. Offline capability/architecture/installer metadata require separate check. |
| Frontend and packaging | `package.json:9`; `scripts/sync_font.py:30-35`; `build_p0_release_candidate.py:81-95` | Font sync writes three files under `public/fonts`. Vite normally empties/replaces `dist/`. PyInstaller with `--noconfirm` writes `release/`, `.qa-p0-pyinstaller` build/spec/work contents and may replace its pre-existing intermediates. It reads `native_app.py`/dependencies; not a dry-run. Existing `dist/` must not be presumed current. |
| QA and production installer *compilation* | `build_p0_release_candidate.py:43-59,97-100`; `madar-update.iss:36-95` | Creates `.qa-inno-v123-integrated/`, executes ISCC twice, produces **separate** QA and production installer files and SHA256 sidecars under `release/`. This **compiles** installers; no setup or service is executed by these calls. The QA Inno configuration uses a segregated install/data/backup root and no uninstall registration; production targets user directories. |
| Final manifest/source check | `build_integrated_v123.py:182-201` | Checks font Git diff, invokes `git update-index --refresh` (modifies index stat cache even without content changes), ensures all three binaries exist, requires source still clean, hashes all outputs and WebView2, writes an exclusive `*.release.json`. **Failed builds may leave partial binaries/sidecars and then be blocked on rerun**. No cleanup or rollback transaction is implemented by the wrapper. |
| *Running* the production setup, **NOT staging** | `madar-update.iss:44-52,78-95,142-197`; `Madar-Upgrade-Preflight.ps1:69-140`; `Madar-Activate-Version.ps1:43-78` | Actual setup may back up the real Roaming MadarDesk profile to LocalAppData, write versioned install files/shortcuts/uninstall metadata, run `/silent /install` WebView2 globally if absent, switch `current-version.txt`/previous-version pointer and write setup logs. No service stop/reconfigure is specified; **not** evidence other users/services are unaffected. **Never run this in the current audit.** |
| Separate WebView2 smoke | `scripts/qa_p0_v123_webview2.py:17-35,198-233` | Creates a dedicated QA AppData + WebView2 profile, launches real `native_app` GUI and writes an acceptance report. This is **not** a source-only preflight and was **not run**. Its checks target the 1.0.23 UI, not proof of an installed setup. |
| Signing and public trust | `scripts/check_release_signing.py:1-33` | Public distribution requires independent valid Windows Authenticode publisher signing. The release manifest's SHA256/size/PE checks establish consistency against manifest bytes, **not independent publisher identity**. No signing or public verification performed. |

### Immutable artifact names for v1.0.23

The wrapper reserves `release/Madar-Desk-v1.0.23-Cumulative-20261107-SettingsTaraz.exe`,
`release/Madar-Desk-1.0.23-Setup-QA.exe`,
`release/Madar-Desk-1.0.23-Setup.exe` and
`release/Madar-Desk-1.0.23-Setup.release.json`, plus three `.sha256.txt`
sidecars; it also treats `release/Madar-Desk-1.0.23-Setup-QA.acceptance.json`
as an exclusive reserved output name. That acceptance JSON **is not generated
by the wrapper's `main()`**, nor was a
`scripts/qa_integrated_v123_installer.py` present at inspection. Therefore
compilation and manifest creation alone cannot be called QA-passed.

## Immediate blockers and assigned follow-ups

1. **P0 / current source cannot be certified.** The current E0–E7 edits are
   uncommitted/untracked, and the integrated builder refuses them. Prime must
   review/test and integrate the intended source into **one clean committed
   candidate revision**, without discarding agent work or treating old HEAD
   as the latest implementation. The pinned 2026-11-07 name/label and version
   `1.0.23` are an older packaging contract, **not proof of current E0–E7
   release scope**; version bump/release identity needs explicit review.
2. **P0 / WebView2 offline binary missing.** Acquire/provision a trusted
   Microsoft-signed, **full offline** x64 prerequisite into the *disposable*
   build tree, verify Authenticode and offline-vs-bootstrapper identity and
   locally record its SHA256. The base script checks signature but not the
   installer channel's full-offline character.
3. **P0 / release QA and E7 are OPEN.** `MTR_E7_ACCEPTANCE_GATES_20261109.md`
   explicitly leaves AC-01..32/G-01..08 open; source/pilot tests and the 4
   new preflight tests are not installation, rollback, official finance,
   two-PC LAN or real user-data safety tests. A v123-specific independent QA
   installer/rollback path and verified manual approval are still needed.
4. **P1 / unverified toolchain/reproducibility.** The base builder assumes
   installed Python/PyInstaller, npm/Vite, Inno Setup 6 at a user-home-derived
   path and suitable fonts; their versions, lockfile fidelity, offline caches,
   program imports and output reproducibility were not checked. Reading
   real profiles merely to discover installed toolchain was out of scope.
5. **P1 / cleanup and collision safety.** Builders write/rewrite `dist/`,
   `public/fonts/`, `.qa-p0-pyinstaller/`, release outputs, QA directory and
   Git index stat metadata; no `--dry-run` or atomic all-output rollback.
   Do not delete/rename previous releases or run a second build over partial
   outputs. **Quarantine a failed disposable environment**, preserve logs,
   start a new disposable environment at the same verified commit. Production
   profiles and installed executables never belong in this cleanup.

## Conditional *offline build-only* procedure for a future authorized RC

The following is a **recipe, not a command run in this audit**. It is safe with
respect to *actual user's installer/service/profile/finance data* only if
executed on a disposable/segregated Windows VM (or equivalently isolated
offline build host) with no mounted operational volumes, no installed Madar
instance, no working LAN peers, no user/Parsian credentials and no external
network, using a fully reviewed *clean committed source*. Simply changing
`TEMP` in the shared Windows session **cannot guarantee** that third-party
build tools will not touch real profile caches. Do not copy the current dirty
worktree wholesale or silently drop its untracked E0–E7 work.

1. Prime selects one reviewed commit **including all intended implementation
   files** and creates a fresh clean checkout at that SHA *inside the VM*,
   excluding any operational files. Verify `git rev-parse HEAD`, empty
   `git status --porcelain=v1 --untracked-files=normal`, no
   reparse/junction paths and no collisions for all immutable release names.
   Keep source and build evidence (commit, lockfile, toolchain versions) together.
2. Provision offline tools only within the VM, including exact tested
   Python/PyInstaller, Node/npm dependencies from an integrity-checked
   lockfile/offline cache, Inno Setup 6 at the **actual path expected by the
   script** (`Path.home()/AppData/Local/Programs/Inno Setup 6/ISCC.exe`),
   and required font assets. Reconcile timestamps/content of synchronized
   `public/fonts` with the clean source; build aborts on real content drift.
3. Place an independently verified, full offline, Microsoft-signed x64
   WebView2 installer at
   `release/.madar-inno-prereq/MicrosoftEdgeWebView2RuntimeInstallerX64.exe`
   in that VM only. `release/` is ignored by the project's `.gitignore`;
   nonetheless **re-check Git clean status** and artifact collisions.
4. **Read-only gate first**, using the VM's Python, without running any
   builder, EXE, Inno setup, smoke or PowerShell upgrade helper:

   ```powershell
   cd 'C:\isolated\Madar-RC-Source'
   py -3.12 -B -m unittest -v tests.test_mtr_package_preflight_20261110
   git rev-parse HEAD
   git --no-optional-locks status --porcelain=v1 --untracked-files=normal
   ```

   The new preflight checks only some preconditions. Independently check
   release artifact collision, prerequisite identity/signature/full-offline
   capability, offline tool versions and E0–E7 targeted + full regression
   results. `current_builder_source_gates_pass=true` is **necessary but
   insufficient**.
5. **Only after those prerequisites and separate build authorization**, the
   exact build-only invocation on that disposable machine is:

   ```powershell
   cd 'C:\isolated\Madar-RC-Source'
   py -3.12 -B scripts/build_integrated_v123.py --webview2 release/.madar-inno-prereq/MicrosoftEdgeWebView2RuntimeInstallerX64.exe
   ```

   Equivalent `npm run dist:rc` is **not** a dry-run and is forbidden in the
   shared worktree. The command above **compiles** application and installers;
   it does not itself run setup, register services or send finance data.
   Verify the exclusive `release.json`, all artifact digests/sizes, clean
   committed source identity and separate signed-release policy after staging.
   Never use `build_p0_release_candidate.py` directly (its raw defaults are
   v1.0.3). Do not use `npm run build` as a release-candidate substitute.
6. No installer execution or upload follows automatically. Separate disposable
   **installer** QA with backup/readback/rollback, real WebView2 smoke, actual
   multi-client LAN, Taraz authority and final E7 matrix approval is required.
   Only a publisher-signed, independently verified release is eligible for
   an explicitly authorized distribution workflow.

**Current answer to the owner:** *Safe offline RC staging is architecturally
possible in a clean, separate build VM; it is NOT safe or runnable as-is in
this shared worktree, and it is not equivalent to distribution readiness.*
No cleanup, installation or packaging was attempted here.

## Follow-on implementation: machine-readable E7 preflight CLI (2026-11-10)

The owner subsequently authorized exactly two NEW source files:
`tools/mtr_release_readiness.py` and `tests/test_mtr_release_readiness.py`.
The CLI is **strictly read-only**. It emits exactly one JSON object to stdout
and exits **2** for `decision=NO_GO`, including unknown/incomplete evidence.
It runs Git metadata *read* commands only (without optional locks and with
filesystem-monitor and lazy network fetch disabled); no builder, installer,
PowerShell signature checker, WebView2 GUI, service or external network runs.

```powershell
# From this isolated Madar repository; safe to run:
py -3.12 -B tools/mtr_release_readiness.py

# For a deliberately created disposable synthetic Git fixture only:
py -3.12 -B tools/mtr_release_readiness.py --root 'C:\synthetic\fixture'

# Regression in synthetic TemporaryDirectory Git roots:
py -3.12 -B -m unittest -v tests.test_mtr_release_readiness tests.test_mtr_package_preflight_20261110
```

An explicit `--root` must be **absolute** and contain a dedicated marker
`.mtr-release-readiness-fixture.json` with exactly
`{"owner":"mtr-release-readiness","synthetic":true}`, plus ordinary
synthetic source/Git files. This deliberately rejects arbitrary real
profile paths, relative paths, symlinks/junctions and linked Git metadata.
The *default* root is the current script's own source tree, with no
synthetic marker needed. On supported platforms all traversed file paths
and ancestors are screened for symlinks/reparse points; this is a source
preflight, **not** a proof against adversarial concurrent filesystem
replacements (TOCTOU).

CLI checks: exact `1.0.23` in package, lock root and updater plus wrapper
`builder.VERSION` and exact `dist:rc` invocation; Git HEAD and full
dirty/untracked status; existence of the offline-prerequisite path (not its
authenticity); existence of the relevant builder/installer-source/toolchain
*source* files; collisions in immutable release outputs/sidecars and QA
intermediates; 32 uniquely identified AC and 8 G status rows. All current
AC/G rows are `OPEN`, hence **BLOCKED**; omitted, duplicate, malformed or
non-`OPEN` rows become **UNKNOWN** rather than self-certifying a release.
`dist/index.html`, even if present, is **UNKNOWN** freshness/provenance.
Installed Node/PyInstaller/Inno toolchain and the signature/full offline
identity of WebView2 are always reported **UNKNOWN** because this tool does
not execute or independently verify them. Therefore JSON `may_build=false`,
`may_install=false`, `may_distribute=false` is intentional.

**Observed final direct invocation:** `py -3.12 -B
tools/mtr_release_readiness.py` printed a single valid JSON record with
`decision=NO_GO`, `source_git.dirty_or_untracked=true`,
`webview2_offline_file.present=false`, `artifact_collisions.state=PASS`,
`builder_sources.state=PASS`, `version_triad.state=PASS`,
`acceptance_ac_g.open_count=40` and `dist.present=true` (unattested);
exit code **2**, as expected. This reports the actual current source tree,
not hypothetical test-only evidence.

**Validation:** `py -3.12 -B -m unittest -v
tests.test_mtr_release_readiness tests.test_mtr_package_preflight_20261110`
**14/14 PASS, exit 0**. Negative cases cover missing WebView2, dirty source,
four version mismatches, falsely reassuring `dist/`, missing/duplicate/
mislabelled AC/G acceptance, pre-existing artifact collision, absent builder
source, relative/unowned root and symlink/reparse path escape. Fixture files,
Git commits and the dummy `WebView2` bytes exist only under disposable
`TemporaryDirectory` roots; the dummy is never executed or accepted as
signed. No real application/profile/service, installer, data, production
accounting or release endpoint was contacted or changed.
