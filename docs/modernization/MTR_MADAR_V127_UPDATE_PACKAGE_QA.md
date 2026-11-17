# Madar Desk v1.0.27 | Offline QA-only update package

**Result (2026-11-10):** Real Windows Inno Setup **QA candidate created**,
**NOT installed / NOT approved for release**. No user profile, existing
installed binary, ledger, service, Git commit/push or network touched.

## Only current candidate: DIR-guarded QA

Installer (19,809,172 bytes):

```text
D:\CoS-Test\MTR-NEXT-UPDATE-CANDIDATES-20261110\madar-v1.0.27\hardened-qa-v127-5ddf1f3e715f\builder\release\Madar-Desk-1.0.27-Setup-QA-DIR-GUARDED-NONRELEASE.exe
```

SHA-256: `97c0b2ba33e8b13ab8b2533a6ebfd940f970ffb9750354f38845186829e5d9fd`

Program payload inside staged builder (18,065,484 bytes):
`Madar-Desk-v1.0.27-QA-ONLY-NONRELEASE.exe`,
SHA-256 `28db6ea51eccbb17d99cccf9111cd934c5e0353fde615e34367825ded228e919`.

Manifest:
`D:\CoS-Test\MTR-NEXT-UPDATE-CANDIDATES-20261110\madar-v1.0.27\hardened-qa-v127-5ddf1f3e715f\qa-update-package-manifest.json`

The compiled Inno Setup PE version is **1.0.27.0**.
Windows Authenticode status: **NotSigned**.

## Real evidence, not inferred installation

- Existing installed version read-only: **1.0.26**; installed binary
  SHA-256 `9bb1471944fc4b31aece7470e9d433fb68e207653d865ca3881c8d5654c943a4`
  unchanged before/after packaging.
- The earlier Sileo/help QA executable was **not renamed** to 1.0.27.
  First, native `madar_update.CURRENT_VERSION` was changed only inside a
  create-only staging copy and PyInstaller rebuilt the v1.0.27 program;
  its embedded Python updater version was read from the PYZ archive.
- Crucial second correction: `src/App.jsx` imports `package.json`; its UI
  therefore displayed `1.0.26` when the prior compiled React bundle was
  reused. A **new Vite build** was produced from all 7,340 previously
  SHA-pinned source/dependency files, with only private package/lock version
  copies changed to 1.0.27. The new compiled JS includes exactly one
  1.0.27 version and no 1.0.26 string.
- New React JS SHA-256:
  `6cbc7d73c7a09fc7992a89372100d92bcf80e61fe336ca72c2d5bde06ba0eb08`.
  The actual PyInstaller PE CArchive contains **all 18** verified newly
  compiled Vite files byte-identically, including Sileo viewport/toasts and
  Persian contextual help.
- Inno compiled using existing audited script copied into private staging,
  **/DQA /DCOMPACT**, and a separate QA AppId.
  The final Inno input is an exclusively created
  `madar-update-QA-DIR-HARDENED.iss`, SHA-256
  `d7fbd3ac90b2ba4b15f9d240d639c8a84d55effd9efe6f40f354123d2c121872`.
- Before *any* preflight/file copy, the staged QA-only Inno script checks the
  normalized `{app}` is precisely the dedicated QA destination and that no
  existing directory component is a symlink/junction/reparse point.
  The post-install pointer activation checks this destination again.
  This addresses a /DIR override escape found during audit.
- If someone explicitly runs the final QA setup, the only approved destination
  is the private
  `...\hardened-qa-v127-5ddf1f3e715f\.qa-inno-v127-20261110\Programs\MadarDesk`.
  **Nobody ran it in this task.** It neither replaces nor updates the
  installed version.

## Earlier candidates are superseded; DO NOT RUN

Two earlier QA Inno setups in this same destination tree lacked the
pre-install **/DIR rejection**. They are retained only because output files
are immutable/create-only. They must **not be executed**. The new marker
`UNSAFE_EARLIER_QA_SETUPS_DO_NOT_RUN.txt` explains this on disk.

## Test scope and remaining NO_GO

Command:

```powershell
python -B -m unittest discover -s tests -p test_madar_v127_update_package_20261110.py -v
```

Tests cover monotonic version, original 1.0.26 binary/source provenance,
single updater version staging, package/lock synchronization, Sileo/help
assets, create-only snapshots, no production installer command, strict QA
path/junction guard and output readback. These are source/static/binary
checks, **not a real installation test**.

**Release remains NO_GO:** unsigned, no staged installer GUI run, no synthetic
upgrade/backup/rollback/3-DB recovery execution, no complete application
acceptance/two-PC LAN TLS test, no official authenticated Taraz finance
receipt, no cleaned/reconciled Git source and no owner release approval.
The original installed program and data are untouched.

This document and the standalone QA script are not a public release plan
approval, permission to install or permission to publish.
