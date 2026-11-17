# E7 actual PowerShell upgrade helpers, disposable synthetic integration QA

**Date:** 2026-11-10. **Disposition:** focused helper-only QA PASS;
**E7 installer/rollback/production acceptance remains OPEN**.

## Scope, ownership and safety

- Only NEW `tests/test_mtr_e7_upgrade_helpers_synthetic_20261110.py` and this
  NEW document were authored by worker-6. Both actual helper sources were
  inspected read-only: `scripts/Madar-Upgrade-Preflight.ps1` and
  `scripts/Madar-Activate-Version.ps1`. **Prime**, not worker-6, applied a
  separate fix to the preflight helper during this task (see reproduced RED
  and GREEN below). Other agents' dirty source was untouched.
- The test actually invokes **those two scripts** with
  `powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File`.
  Each test creates a separate `tempfile.TemporaryDirectory` named
  `.qa-inno-v123-<random>`, with `Roaming\MadarDesk`, `Snapshots`,
  `Programs\MadarDesk`, and synthetic environment directories exclusively
  inside that one new directory. `APPDATA`, `LOCALAPPDATA`, `USERPROFILE`,
  `HOME`, `TEMP`, `TMP` and `WEBVIEW2_USER_DATA_FOLDER` passed to
  PowerShell are redirected to synthetic test directories.
- The harness validates every helper input as an **absolute** path inside
  the test-owned temporary directory, denies `..`, parent/root/repo paths
  and reparse-point paths, and allows a deliberately created linked path
  *only* when its resolved target also lies inside that same disposable
  directory. The normal preflight wrapper allows only
  `<QA_ROOT>\Roaming\MadarDesk`; the one intentionally malformed DataRoot
  test passes a different name **still within QA_ROOT** to prove the actual
  helper refuses it. No real user or installed paths were provided.
- Fake EXE payloads are plain synthetic bytes, never launched. They test
  digest/pointer behavior, **not** the validity or Authenticode of a Windows
  program. The tests perform no Inno installer, WebView2 installation,
  native app launch, Windows service operations, network, customer profile,
  genuine financial operation, commit, push or deploy.
- Source SHA-256 snapshots are checked before/after each test to ensure
  neither PowerShell helper is modified by its invocation. ZIP backup
  assertions independently reopen the generated archive and compare exact
  per-file content, size and SHA-256, including a nested UTF-8 file and binary
  payload, and ensure no `.partial` file remains after success.

## Safety defect reproduced and subsequently corrected by prime

**Before the prime patch:** `Madar-Upgrade-Preflight.ps1 -IsolatedQA` checked
the `DataRoot` regex and rejected backup/data overlap and reparse points,
but did **not** require the actual Inno QA backup path
`<QA_ROOT>\Snapshots`. A non-overlapping `<QA_ROOT>\OtherBackups` was
accepted, even though QA must not write to caller-selected backup locations.

`test_isolated_qa_rejects_nonsibling_backup_inside_disposable_root` initially
ran on a brand-new synthetic root with a synthetic file and produced
**FAIL, 1 test, exit 1** because the actual helper returned success for
`-BackupRoot <QA_ROOT>\OtherBackups`. This is a real, bounded negative
reproducer, not a simulated failure. No outside/test-unowned path was used.

**Prime-owned fix, separately observed in Git diff:** on `-IsolatedQA`,
the helper derives `QA_ROOT` from the validated `DataRoot` and requires
the normalized `BackupRoot` to equal `QA_ROOT\Snapshots`
case-insensitively. Normal overlap and reparse guards remain. Worker-6
did **not** edit this pre-existing script.

The same negative test later returned **PASS**, and all focused tests
passed after prime's patch. This establishes the narrow source-level
backup-destination behavior for synthetic paths only, not acceptance of
a real installation or proof against concurrent malicious filesystem swaps.

## Executed scenarios and results

Exact command in the isolated Madar source worktree:

```powershell
py -3.12 -B -m unittest -v tests.test_mtr_e7_upgrade_helpers_synthetic_20261110
```

**Final observed result: 13 tests, OK, exit 0, 11.351 seconds**. Coverage:

1. Backup: new synthetic profile produces `FRESH_PROFILE` without a ZIP;
   three existing files are archived with matching per-file SHA-256/size/bytes
   and intact originals; successful ZIP readback has no CRC errors or
   stray `.partial` file.
2. Backup rejection: three overlap relationships; a synthetic linked folder
   under DataRoot; a linked `Snapshots` directory whose target is also
   disposable; malformed synthetic QA `DataRoot`; and a nonsibling backup
   destination `OtherBackups`. All negative cases reject without publishing
   an archive or modifying the synthetic source data.
3. Activation: first version pointer, upgrade `1.0.22 -> 1.0.23`, previous
   version pointer and same-version idempotency; implicit downgrade
   `1.0.23 -> 1.0.22` denied with pointer unchanged; explicit
   `-AllowRollback` and matching digest accepted with previous pointer
   updated correctly.
4. Activation rejection: wrong SHA-256, absent version EXE, invalid version
   path string, malformed prior pointer, linked pointer resolving to synthetic
   target, and Python-level denial of all paths outside fresh QA root.

The suite reported no skipped tests in this execution. Python 3.12 used
`-B` to suppress bytecode writes, and all subprocess helper writes were
limited to newly generated temporary paths. The earlier failed full run
before the final 13/13 contained a **test-fixture-only** regular-expression
error: `TemporaryDirectory` sometimes generates an underscore in its
random suffix, while the initial test assertion disallowed underscores.
The test guard was corrected to accept `[A-Za-z0-9_-]+` while retaining the
mandatory `.qa-inno-v123-` prefix.

## Residual limits and E7 release gates

- **Not an installer test.** No built setup, Inno `PrepareToInstall`,
  physical Windows app, real WebView2 engine, actual install directory or
  service coexistence test was executed. The real LAN and two-PC scenarios
  are not covered.
- **Not a real-data backup/restore/rollback test.** ZIP fidelity applies
  only to a small controlled fixture. Recovery from partial disk failure,
  file locks/concurrent writers, large/historical profiles, permissions/ACL,
  interrupted snapshot and installed migration need separate safe trials.
  Testing that a version pointer changes does **not** prove the old program
  boots, its data migrates backward or restored data remains compatible.
- **No signed executable validation.** Activation only checks that the
  *provided* SHA-256 matches the target file. A caller-supplied digest
  alone does not prove publisher authenticity or valid/working PE bytes.
  This suite intentionally supplies fake EXE content and never executes it.
- **No production-authority claims.** It neither authenticates Taraz nor
  verifies financial posting, document receipt, or E0-E7 full integration.
  All `AC-01..AC-32` and `G-01..G-08` acceptance gates remain OPEN
  independently of these helper checks.
- **Trust boundary:** a caller with direct access to these scripts may
  pass arbitrary paths outside the synthetic test harness; the harness
  prevents that *here* but is not a production security boundary. The new
  `-IsolatedQA` sibling backup validation narrows this gap for QA runs,
  while elevated-path/TOCTOU scenarios require separate hardening review.
