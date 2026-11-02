# Madar Desk 1.0.3 RC | P0 source and installer acceptance

## Source and scope

- Isolated branch `modernization/phase4-20261102` and worktree `D:\CoS-Test\madar-codex-modernization-phase2-20261101`.
- Integrated `main` through `6f1ae6f26efc20cbac5fcc6fc5393063c324f938` in merge commit `31c85631b3f7288ef87c6bbfcba5251a528261dd`. Both the secure unique temporary user-registry writer and the earlier non-mutating deletion code were preserved. The integrated 12-test LAN persistence module passed before the P0 journal was introduced.
- Release version incremented from 1.0.2 to **1.0.3** because versioned binaries must never be silently overwritten. `package.json`, root entries in `package-lock.json`, and the Inno compiler macros use that version.

## P0.1: Cross-file LAN deletion recovery

- A persistent, versioned `users.json.delete-pending.json` intent is atomically written **before** changing either the account registry or task assignments. Host initialization completes a valid pending intent before opening a listener; malformed/linked/oversized intent is refused.
- Normal delete success preserves all unrelated assignments, revokes only deleted-user sessions, and clears the intent. Synthetic ordinary failure paths attempt compensation; if compensation fails, requests are fail-closed and restart recovery completes the deletion.
- Two **actual subprocess hard-stop tests** exited with codes 71 (after user registry write) and 72 (after task-state write). New LAN host constructions completed the pending deletion, preserving unrelated assignees and yielding a consistent user registry and card store. Restart was idempotent. Malformed intent failed closed without mutating either store.
- Limitations: a process hard-stop is **not** a physical power cut. Directory durability after a sudden storage outage, a disk that lies about flushes, concurrent independent LAN hosts targeting the same two files, or failed post-error compensation still need a specialized operational audit. Do not state that power-loss safety on real hardware was proven.

## P0.2: Release artifacts and prerequisites

Build script: `python -B scripts/build_p0_release_candidate.py --webview2 <absolute path to a signed offline Microsoft WebView2 runtime>`.

The locally used offline WebView2 prerequisite was checked with Authenticode: **Valid**, publisher **Microsoft Corporation**, SHA-256 `9B0142E22E8DAA92855D746AE4D1E9EEEF561CCAF67D1DD452165C4AF3DF3191`. The source file was copied into this isolated worktree's ignored release directory and byte-hash checked. This installer payload is not stored in Git.

| Artifact (ignored `release/`) | SHA-256 from build verification |
| --- | --- |
| `Madar-Desk-v1.0.3-RC-20261102.exe` | `9f7cdc3f2af33d791414b7d2c5abcc12f1d11c87e9ea0a27716b435234b46db6` |
| `Madar-Setup-v1.0.3-RC-20261102-QA.exe` | `562632de6aa6168d670f71a88a29d8dd9b201c75fc6ab3518b914c539de1702a` |
| `Madar-Setup-v1.0.3-RC-20261102.exe` | `a838e8ada4b8ce402ad9835421c23020704aa09efd0e24450c80d2f175af30f3` |
| `Madar-Setup-v1.0.3-RC-20261102-QA-Fresh.exe` | `1c33fc5f01cfa8b3ee57dc12f54c8dab2a86b321ed4f194135299f7dfe6ac2bb` |

All QA setup binaries use the dedicated QA app ID and built-in QA paths, not the customer's APPDATA. The production setup was **built, not installed**. These EXEs have not been digitally signed for public distribution. No production user's data, real installed Madar or Parsian backup was accessed by these release tests.

PowerShell `Get-AuthenticodeSignature` on the production installer specifically returned **NotSigned**; independently queried `Get-FileHash` confirmed its SHA-256 `A838E8ADA4B8CE402AD9835421C23020704AA09EFD0E24450C80D2F175AF30F3` and size **231,521,620 bytes**. SmartScreen / antivirus acceptance is not inferred.

## P0.3: Executed installer QA

- `python -B tools/p0_installer_acceptance.py`: **exit 0** / `RC_ISOLATED_INSTALL_UPGRADE_ROLLBACK_PASS`. Actual Inno QA installer installed a byte-matching v1.0.3 executable next to an existing synthetic v1.0.2 executable. Three source profile files (tasks, identity, attachment) stayed byte-identical; a single full verified ZIP was written before pointer switch. Both rollback to v1.0.2 and reactivation of v1.0.3 succeeded without touching those files.
- `python -B tools/p0_fresh_installer_acceptance.py`: **exit 0** / `RC_FRESH_INSTALL_PASS`. A separate actual Inno QA installer activated v1.0.3 in a clean isolated profile with a matching executable checksum and no automatically seeded task file. The only persistent QA files are under `.qa-*` and ignored `release/`.

## Source validation and release restrictions

The official `npm test` is the isolated launcher: one disposable Windows profile per Python module, Vite build before serial browser UI checks, and no installed executable or live finance data involved. **Post-change execution returned exit 0**: Python **172/172 executed modules**, **1,652 tests reported**, 2 skips, 2 expected failures, zero unexpected errors/failures/timeouts; Vite build PASS; Node/React/Playwright **530/530 PASS**, zero skips. The separate packaged host EXE opt-in test was excluded as designed.

This RC is suitable for **supervised user-install acceptance** only when full source gates and final SHA readback are green. It does not approve public distribution, AV/SmartScreen, hardware power-loss certification, two-physical-PC LAN, or actual Parsian multi-year financial migration. Those are separate release gates.
