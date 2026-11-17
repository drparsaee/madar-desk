# Madar 1.0.26 | independent Sileo + contextual-help Windows EXE QA

**Result:** `QA_WINDOWS_EXE_EMBEDDED_VITE_VERIFIED_NO_INSTALL`.
Classification: **QA-only, NONRELEASE, not installed, unsigned**.

## Exact evidence, 2026-11-10

- Built with local **PyInstaller 6.22.3** (`--onefile --windowed --noupx`)
  from **pinned, already compiled Vite assets**, not the currently dirty
  `src/App.jsx`.
- Pinned Vite QA run:
  `D:\CoS-Test\MTR-MADAR-SILEO-QA-20261110\run-20261110-163354-67a1ede34858`.
- Its immutable `source-manifest.json` SHA-256:
  `33a9c9aec67d6c2175e1feb7e07d75748bdcfe58a50c6faebeb30c6e811d1553`.
- Prior Vite QA source inventory SHA-256:
  `b8d2b61392c467765b395f261b3587ec3161bb3475a444bddb751ccf9a3d1768`.
- Prior Vite npm dependency inventory SHA-256:
  `a30fc49c4517f46179b0859880dc42039e11635758e35a495e90c183417964ee`.
- Prior compiled Vite `assets/main-Cd8KyHQW.js` SHA-256:
  `f2c5f5c495482ca6fd6271e04eb4212e6b407ee775b44f90c3ab72bc13281856`.
- The original Vite source snapshot contained `native_app.py` and
  `madar_update.py`, which were copied **only from that pinned snapshot**.
  Another **98** top-level Python dependency modules needed by the native
  entrypoint were copied into an independent create-only layer, each with
  SHA-256 readback. Supplemental Python map SHA-256:
  `bccdc21dd8c0b2641b2f43f19219c0b7cbd09b38d0c52b5585faf35b2d19e1a3`.
- PyInstaller ran from this independent Python layer, with all temporary,
  APPDATA/LOCALAPPDATA, user-home, and build caches diverted to a private QA
  directory. No existing source files, installed EXE, or user profile data
  were changed by this build.

## Verified binary

File:
`D:\CoS-Test\MTR-MADAR-SILEO-QA-20261110\exe-only-20261110-164543-5e6ab975712e\exe-dist\Madar-Sileo-Help-v1.0.26-QA-ONLY-NONRELEASE.exe`

- Windows MZ executable, **18,067,307 bytes**.
- SHA-256:
  `f2d161bfc41576beb0dbd28cd8bb6154a32ffeb8cd69e15e0eca75bb24973468`.
- Opened the **actual PyInstaller CArchive inside the EXE**, extracted
  **all 18 embedded Vite assets**, and compared their uncompressed bytes and
  SHA-256 against the exact previously verified Vite output.
- Specifically confirmed the embedded JS includes
  `data-sileo-viewport`, `data-sileo-toast`,
  `mtr-context-help__trigger` and the Persian heading
  `راهنمای مدار`. This is evidence of embedded compiled features, not
  evidence that every user journey works in a Windows GUI.
- The build script reverified the pinned source/dependency/compiled assets
  after packaging and rechecked the supplementary Python sources.
- The installed `%LOCALAPPDATA%\Programs\MadarDesk\current-version.txt`
  remained **1.0.26** before and after packaging. Installed
  `versions\1.0.26\Madar-Desk.exe` remained the exact same
  **17,981,900-byte** file with SHA-256
  `9bb1471944fc4b31aece7470e9d433fb68e207653d865ca3881c8d5654c943a4`.
  **NO overwrite, downgrade, activation or installation.**

Create-only report:
`D:\CoS-Test\MTR-MADAR-SILEO-QA-20261110\exe-only-20261110-164543-5e6ab975712e\qa-exe-report.json`

## Tests

```powershell
python -B -m unittest discover -s tests -p test_mtr_sileo_v126_pinned_exe_20261110.py -v
```

**9/9 passed**. Tests verify the pinned actual Vite manifest, immutable
Python entrypoint snapshot, private build environment, no installer command,
no installed downgrade, and positive/negative synthetic PyInstaller-archive
extraction (missing/tampered frontend fails closed). Earlier QA evidence
included 10/10 snapshot-gate tests, 9/9 context-help tests and 12/12 Sileo
tests, but these are separate previously recorded runs.

## Outstanding release gates: NO_GO

- No installer created, no signing, no commit, no push, no deployment or app
  activation. The source worktree is detached/dirty and **not approved for
  a same-version production replacement**.
- No synthetic packaged WebView2 GUI process was launched in this step:
  the native app starts a local HTTP listener and scheduled background jobs,
  so launching it is not necessary for the requested independent binary
  provenance proof and would broaden the no-profile/network scope.
- Native archive packaging is not a full two-computer LAN, live hosted
  authorization, financial migration, receipt issuer, or recovery test.
  `officialFinanceReceiptVerified` remains **false**.
- A later isolated GUI run with explicit disposable profile, independent
  feature checks, source-release reconciliation, signing/release approval,
  and separate non-downgrade migration validation are still required.

The user-installed v1.0.26 is **not** the newly built QA EXE. Treat the QA
artifact strictly as a local, unsigned inspection candidate.
