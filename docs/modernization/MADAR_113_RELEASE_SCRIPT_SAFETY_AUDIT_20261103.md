# Madar Desk 1.0.13 release-script safety audit (source only)

**Audit base:** isolated Git `d56486d91a0ee3b4b709d51dd4c9d894f3d75912`, November 3, 2026. Canonical `main` reported as `6bf687b`; installed app reported as `1.0.12`. These are **inputs to the assignment**, not independently inspected installed-app evidence. Prime owns release after UX **10/10** and integration acceptance.

## Files examined

`scripts/build_integrated_v113.py`, `scripts/build_p0_release_candidate.py`, `scripts/qa_integrated_v113_installer.py`, `scripts/qa_integrated_v113_native.py`, `scripts/madar-update.iss`, `scripts/Madar-Upgrade-Preflight.ps1`, `scripts/Madar-Activate-Version.ps1`, `tests/test_cumulative_113_update.py`, plus packaging/version metadata and `native_app.py`'s QA bridge path. **No builder, Inno installer, QA executable or installed app was launched in this audit.**

## Findings and bounded fixes

| Risk | Evidence in original source | Applied hardening | Limitation |
| --- | --- | --- | --- |
| QA executable not authenticated against manifest | The v113 manifest pinned production installer and program only, while QA runner executed `builder.QA` | Schema 2 pins SHA256 **and size** for program, production installer and **QA installer**; verify exact filenames and distinct QA/prod hashes **before** synthetic QA runs | A JSON manifest and hashes are *not* publisher signatures; tampering with manifest and binaries together remains out of scope |
| Native smoke could launch arbitrary PE | Native smoke only checked `MZ` | Verify manifest and exact candidate program SHA256/size before launching; recheck program hash immediately before `Popen` | No actual WebView2 smoke performed; executable trust/authenticity still requires independent code-signing verification |
| Untracked/dirty release inputs and stale receipts | Original builder did not pin Git source or reject stale SHA sidecars | Require committed clean Git tree; record full source commit SHA; refuse existing QA acceptance/sidecars/release outputs, verify SHA after building | Git commit identifies source state; it **does not** prove reproducible byte-for-byte builds across toolchain machines/timestamps |
| QA path redirection/profile contamination | Original runner allowed preexisting empty QA_ROOT without symlink/junction screening | Verify fixed repo-local `.qa-inno-v113-integrated` root and all ancestors; reject links/junctions and nonempty target; explicitly pass `/DIR=<isolated QA install>`; verify profile snapshots and old binary; cleanup only owned directory | QA binary directly invoked with arbitrary external switches has not been penetration-tested. Do not distribute QA installer to users |
| QA success evidence disappeared with cleanup | Original script printed a success line then deleted QA root and log | Write immutable QA acceptance JSON in release after all checks/cleanup, containing input hashes, 1.0.12→1.0.13, synthetic profile/backup counts and log SHA256 | Acceptance JSON is a runner receipt; full raw Inno log is intentionally not retained by the current runner |
| Native QA inherited genuine Windows identity/home | Original runner replaced APPDATA/LOCALAPPDATA/TEMP/TMP only | Redirect HOME, USERPROFILE, HOMEDRIVE/HOMEPATH too; remove project credential prefixes/PYTHONPATH/PYTHONHOME before process start | Native Windows known-folder APIs may still resolve real user directories. The tested `bridge-readiness` path is a narrow smoke, **not** global no-data-access proof |

## Existing installer protections observed in source

`madar-update.iss` uses side-by-side binary location `versions/<version>/Madar-Desk.exe` and `onlyifdoesntexist` rather than overwriting APPDATA. It invokes PowerShell preflight first and activation last. Preflight verifies a source profile ZIP by file count, sizes and SHA256 content, rejects linked paths and source/backup overlap. Activation hashes the target executable and rejects silent downgrades. The source synthetic upgrade suite tests 1.0.12 to 1.0.13 pointers and byte-preservation. These are **source/runtime-in-synthetic-temp observations**, not evidence of an executed v113 Inno installer.

## Required release sequence and remaining gates

1. Prime integrates reviewed fixes, commits a **clean** source state and achieves UX 10/10. The version must consistently be `1.0.13` across package, npm lock and `madar_update.py`.
2. Run `python -B scripts/build_integrated_v113.py --webview2 <existing-signed-offline-WebView2-prerequisite>` in an authorized release workspace. This audit **did not** run it. Build output must contain a schema-2 manifest, exact SHA256 for all three binaries, prerequisite hash, source commit and 1.0.12 cumulative target.
3. Independently verify the committed source and toolchain. Byte-identical deterministic rebuild requires **two separate clean builds and comparing actual SHA256 outputs**; it was **not demonstrated**. Output hashes in a manifest only pin the single observed build.
4. Run isolated QA only: `python -B scripts/qa_integrated_v113_installer.py`, which must exit successfully and leave an immutable `Madar-Desk-1.0.13-Setup-QA.acceptance.json` with `result=synthetic-installer-passed`. Verify receipt SHA references match the release manifest; do not execute QA outside the fixed runner.
5. Run native WebView2 QA *only in an authorized disposable Windows environment*, inspect its synthetic-only read result, and complete prime's UI/regression/security gates. Keep installed 1.0.12, user APPDATA, real Parsian/finance data and canonical main unchanged until actual release authorization.

## Tests actually run

Commands on this isolated source checkout:

```powershell
python -B -m unittest -q tests.test_integrated_v113_release_audit_20261103
python -B -m unittest -q tests.test_cumulative_113_update
git diff --check
```

`test_integrated_v113_release_audit_20261103.py` uses disposable synthetic MZ byte strings, temporary files and mocked Git/native/installer calls; it never builds/launches anything. It also simulates a **successful Inno output** inside a temporary QA root to verify the *runner's* version-pointer checks, six synthetic files, ZIP backup match, cleanup and immutable acceptance receipt. The Inno process in this test is **mocked**, not executed. `test_cumulative_113_update.py` executes the PowerShell preflight and activation helpers only against temporary synthetic paths, not an installer or user profile.

**No production binary hash or installer acceptance status is claimed by this document.**
