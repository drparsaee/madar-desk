# Madar ↔ Taraz P0: version-safe source lineage and upgrade gate

**2026-11-10 | Read-only audit | `NO_GO / NO_DOWNGRADE`**

## Decision and evidence boundary

The current shared Madar worktree is a **1.0.23 source line**. The separately
observed installed baseline is **1.0.26**. Building, renaming, or installing a
1.0.23 artifact over 1.0.26 would be a downgrade even if the latest source has
newer Madar ↔ Taraz code. The next eligible release number is **at least 1.0.27
only if an independent readback still confirms 1.0.26 as the installed version**.
Neither the existing QA bundle nor this document authorizes an installation.

This audit examined the current dirty source, **local Git references only**,
the latest external QA-only bundle **read-only**, and the existing Inno/updater
source. No Git fetch, installed app or private profile inspection, build,
network operation, installer, financial operation, commit, push or deployment
was performed. A reported installed hash is cited as **prior recorded evidence**,
not newly re-read here.

## Independently observed version origins

| Source or artifact | Version | Exact identity / qualification |
|---|---|---|
| Current P2 worktree `feat/madar-p2-gantt-notifications-20261107` | `1.0.23` | `HEAD=32bd8ffe5ebbb0f4cd5c011c59323ed32f8647ac`; `package.json`, both lockfile root fields, `madar_update.CURRENT_VERSION` and `scripts/build_integrated_v123.py` agree |
| 1.0.24 P0 side candidate | `1.0.24` | Local branch `feat/madar-v124-p0-rc-20261107` at `f0fff5cf5d0d0a05c8fa2e45aaa47b22fac7b63f`; QA-specific build route `scripts/build_p0_v124_qa.py`, **not shipped evidence** |
| 1.0.25 P1 QA ancestor | `1.0.25` | `feat/madar-p1-v125-qa-20261107` at `41dcf41c32a57daeb14dd71ff05dd2a9500c53c5`; QA build route `scripts/build_p1_v125_qa.py` |
| 1.0.26 P1/P2 integration branch | `1.0.26` | `feat/madar-v126-p1p2-github-20261107` at `785a419af482f998154464a41df7770c9c9c87d4`; `scripts/build_p1p2_v126_qa.py`, matching package/lock/updater version metadata |
| Local tracking `origin/main` | `1.0.13` | `c9aaf3e4a9cd7653a620d3671ffc58f546c3d17e` at inspection; **local ref**, not a fresh server check or safe upgrade base by version |
| Installed Madar | **reported/previously inspected** `1.0.26` | `docs/modernization/MTR_INSTALLED_LOCAL_BRIDGE_PROOF_20261110.md` records `MadarDesk/versions/1.0.26/Madar-Desk.exe` SHA-256 `9bb1471944fc4b31aece7470e9d433fb68e207653d865ca3881c8d5654c943a4`; not re-inspected in this task |

**Critical Git-graph distinction:** local `git merge-base --is-ancestor`
confirms that `41dcf41` (1.0.25) **is an ancestor** of `785a419`
(1.0.26). It confirms that `f0fff5c` (the separate 1.0.24 P0 candidate)
**is not an ancestor** of either 1.0.25 or 1.0.26; their merge-base is
`5a0b4c2623d5f34a86a36b129970695ee5278a83`. Thus the 1.0.26 branch
document's phrase “descended from the frozen 1.0.24 P0 candidate” describes
*claimed feature lineage*, not literal ancestry of the frozen candidate
commit. Audit P0 feature equivalence before accepting it as preserved.

**Also critical:** neither current `32bd8ff` nor 1.0.26 `785a419`
is an ancestor of the other. Their merge-base is
`0b6abb980da90bd5c22f765414e92d4a58bcf383`. Relative to that
base, Git reports **23 commits on the 1.0.26 branch and eight commits on the
current HEAD**. The 1.0.26 branch has P2 changes replayed/cherry-picked with
distinct commit IDs. Treating the 1.0.23 working tree as the new release base,
or blindly merging its commits into 1.0.26, can drop or duplicate shipped P1/P2
behavior. Comparing `HEAD` to `785a419` currently shows 70 changed tracked
files, including differences in `src/App.jsx`, `src/startup_update.mjs`,
`madar_update.py`, `package.json`, `package-lock.json`, release wrappers and
Web/PWA modules. This comparison is committed HEAD-to-HEAD only: **274
modified/untracked paths** were also present in the shared worktree when
counted, outside that Git diff, and other workers can change that count.

## Installer and updater contract (source reviewed, not executed)

- `package.json` → `dist:rc` selects the version-specific builder, which
  enforces matching package/lock/updater inputs and immutable output names.
  Current branch selects the **1.0.23** builder; the 1.0.26 line selects
  `scripts/build_p1p2_v126_qa.py`. Merely editing a JSON version is insufficient.
- `scripts/build_p0_release_candidate.py` passes `/DMadarVersion=<version>`
  and `/DExeFile=<binary>` to `scripts/madar-update.iss`. Inno uses
  `AppVersion={#MadarVersion}`, `VersionInfoVersion={#MadarVersion}.0`,
  and stores `Madar-Desk.exe` under `versions/<version>` with
  `onlyifdoesntexist`. Its standalone historical fallback is `1.0.2`, so
  **do not call Inno without explicit, validated builder overrides**.
- `scripts/Madar-Activate-Version.ps1` compares target and existing version
  and rejects a normal downgrade without an explicit `-AllowRollback` switch;
  it checks target binary SHA-256 and current pointer integrity. That rollback
  path is not an upgrade shortcut and was **not run** in this audit.
- `madar_update.py` selects only stable, newer GitHub releases and requires
  an exact versioned installer name, trusted URL, SHA-256 and byte size.
  The 1.0.26 integration also has startup download-to-cache behavior via
  `src/startup_update.mjs`; an actual install still requires explicit user
  action. A 1.0.23 binary must not be relabeled as 1.0.27.
- The **current** release readiness tooling is anchored to 1.0.23
  (`tools/mtr_release_readiness.py` and `scripts/build_integrated_v123.py`).
  New version tooling and pins require separate reviewed source changes
  in a future release branch, with no weakening of gate checks.

## Latest nonrelease QA candidate: actual on-disk hash evidence

Folder:
`D:\CoS-Test\MTR-MADAR-TARAZ-QA-BUNDLE-20261110\run-20261110-183506-18748-ec491e30`

| Read-only file/manifest | Directly observed value |
|---|---|
| `exe-dist/Madar-Taraz-Connection-QA-20261110-NONRELEASE.exe` | 18,162,253 bytes; SHA-256 `0ba37c211f738d3d7bb9cf2a794a904f0269de128f72dfa8f1662755ac719454` |
| `qa-provenance.json` | SHA-256 `0689d26c3a554bef7995abf51b038c49af050adb44a86563a3227a6da92ee297` |
| `qa-build-result.json` | SHA-256 `58a9dd6a793b9c0c0c5ffc07032a0ba57090bf97a9d20ec51a47ee8f18c61a73` |
| `source-input-sha256.json` | SHA-256 `101e2f846ea1e5b19214a5a397958256432281d9a4430649a0fc696e464993b9`; reports **6,502 inputs** and source-tree SHA-256 `1f4853ff34db15dbe49281003f15cbe0ec1ea39689ac7dafe267409bc3409617` |
| Bundled source version inputs | `source/package.json=1.0.23`, both root lockfile versions `1.0.23`, `source/madar_update.py=1.0.23` |

An independent **read-only full inventory recomputation** opened and SHA-256
hashed all **6,502** recorded files under the bundle's disposable `source/`
snapshot (**98,101,454 file bytes**): zero file hash/size mismatches. It also
recomputed the recorded tree digest from the sorted `path + NUL + sha256 + LF`
inventory entries and obtained exactly
`1f4853ff34db15dbe49281003f15cbe0ec1ea39689ac7dafe267409bc3409617`.
This verifies the bundle's snapshot bytes against its own manifest and the
independently supplied tree pin; **it does not verify an installed program or
identify a clean canonical Git commit**.

The bundle itself declares `QA_BUILT_NON_RELEASE`, `QA_ONLY_NON_RELEASE`,
`application.releaseReady=false` and `notFunctionalTestOrReleaseApproval=true`.
Both its build result and provenance **lack explicit `appVersion`**. The
existing independent parity checker therefore returns **`BLOCKED`**, including
`candidate_must_be_newer_than_installed` and
`missing_or_mismatched_qa_embedded_version`, even when the supplied QA EXE,
provenance and source-tree pins match the actual local bytes. The source pin
required by that checker is independently missing. Checks of seven selected
working-source files found matching hashes for five that occur in the QA source
inventory (`package.json`, `package-lock.json`, `madar_update.py`,
`native_app.py`, `src/App.jsx`); the old `v123` builder and
`Madar-Upgrade-Preflight.ps1` **are not in that QA snapshot inventory**. Those
matches cannot attest a full installable release source tree or a current
committed release. Even byte-for-byte matching of the QA archive cannot
establish Authenticode trust, finance authority, absence of regression or
production install safety.

## Proposed safe integration lineage (future work, not applied)

1. **Protect the current evidence.** Record independently the installed
   baseline version, SHA-256, release provenance and which source commit
   produced it; check current pointers via an authorized operator readback.
   Do not conflate a directory named `1.0.26` with a verified source lineage.
2. **Use the strongest local 1.0.26 lineage as integration baseline:**
   `785a419` descended from `41dcf41` (P1). Compare and reconcile *content*
   from the frozen 1.0.24 P0 side branch (`f0fff5c`) and P2 current branch.
   Verify that P0 fixes, P1 permissions/offline tests, P2 Native/Web features,
   update caching and installer contracts remain intact. Verify exact divergence
   with three-way diff and per-feature tests; use selective integration to
   avoid duplicate P2 cherry-picks or reverting later code.
3. **Promote the reviewed Madar ↔ Taraz changes**, especially the newer manual
   Prepare/Queue/History UI and peer-trust checks, from the concurrently dirty
   P0 workspace onto a new isolated candidate descendant of the reconciled
   1.0.26 line. Review conflicts, deleted paths, moved finance APIs and any
   race/crash/retry behavior. Preserve the current version metadata until the
   resulting source and complete regression suite are verified.
4. **Only then assign a genuinely newer version.** For a verified installed
   baseline of 1.0.26, minimum `1.0.27`; if a later baseline exists, choose a
   version *strictly greater* than that instead. In the *future release branch*,
   align `package.json`, both root `package-lock.json` versions,
   `madar_update.CURRENT_VERSION`, versioned builder route, builder VERSION,
   installer base/output/version metadata, release manifests and all readiness
   tests. Derive the new wrapper from the **reconciled 1.0.26 P1/P2** builder
   requirements, rather than assuming the earlier v123 wrapper covers P1/P2.
5. **Build a fresh QA-only artifact from an exact clean source commit**, with
   independent full-source SHA inventory and externally pinned QA EXE,
   provenance, snapshot, bundled UI/assets, and an explicit source-bound
   `appVersion` in both the build result and embedded QA provenance. Confirm
   immutable installer names. Run comprehensive current-architecture + full
   legacy classification, PyInstaller archive/version checks, isolated UI,
   cross-app identity/recovery and disposable install/rollback tests on the
   **new exact candidate**. Compare the verified 1.0.26 baseline behavior to
   the new candidate using the same fixtures; record actual differences.
6. **Pass independent release gates before seeking install approval:** official
   Taraz financial authority/receipt and duplicate prevention, two physical
   Windows clients, full backup/restore and power-loss recovery, validated
   Windows signing and all 40 E7 AC/G gates. Owner signing is currently
   deferred for QA only. No unsigned QA build becomes a production release
   merely because its version is newer.

### Reproducible, read-only checks

Run in this isolated Madar worktree; no remote fetch is implied:

```powershell
git rev-parse HEAD
git show feat/madar-v126-p1p2-github-20261107:package.json
git show feat/madar-v126-p1p2-github-20261107:madar_update.py
git merge-base HEAD feat/madar-v126-p1p2-github-20261107
git merge-base --is-ancestor feat/madar-p1-v125-qa-20261107 feat/madar-v126-p1p2-github-20261107
git diff --name-status HEAD feat/madar-v126-p1p2-github-20261107
git status --porcelain=v1 --untracked-files=normal
python -B -m unittest discover -s tests -p test_mtr_release_version_parity_20261110.py -v
python -B scripts/qa_mtr_release_version_parity_20261110.py
```

The last audit is intentionally expected to exit **2 / BLOCKED**. A passing
unit test is evidence only for the cases it executed. All 40 E7 acceptance
rows remain OPEN in the available review evidence. **No real upgrade,
zero-regression claim, or production release is established here.**
