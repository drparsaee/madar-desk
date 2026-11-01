# ExecPlan | Fail closed on reparse/junction paths during version activation

## Purpose and boundaries

Owner goal: retain data and trustworthiness of Windows upgrades. Current branch starts at commit `60beedd`. Only synthetic activation binaries and disposable installation directories may be used. No installed customer EXE, APPDATA or Parsian database is touched.

## Current observed contract and reproduced defect

`scripts/Madar-Activate-Version.ps1` validates absolute install root and the executable SHA-256 before atomically moving the version pointer. Unlike the preflight backup script, it does not inspect reparse/junction paths. That allows an attacker-controllable version directory link to point outside the intended install root. A valid matching SHA-256 then triggers activation of the linked executable.

Before code changes, `tests.test_madar_update_contract.UpgradeTests.test_activation_refuses_junction_to_external_version_directory` **failed**, with `VERSION_ACTIVATED: 1.0.3` and exit 0 on a synthetic Windows junction pointing to a separate disposable folder, when the safe expectation was refusal.

## Plan and parity

1. Reject existing reparse points in the explicit installation root's ancestors, the selected executable's ancestors, and the active/previous version pointer paths before hashing or modifying files.
2. Keep existing version SHA, active/previous pointer, rollback and same-version repair contracts unchanged.
3. Run the new negative fixture plus all updater/restore parity tests under disposable APPDATA and LOCALAPPDATA, and inspect `git diff --check`. Reproduce existing tests on both old and new paths where possible.

## Limits

This guards ordinary detectable Windows reparse points. It is not an ACL audit, code-signing validation, protection against a malicious local administrator racing a directory swap, or production installer approval. Full Python regression and real multi-device upgrade testing remain release gates.

## Implemented and observed

- **Before patch:** the synthetic version-1.0.3 junction fixture returned `VERSION_ACTIVATED: 1.0.3` (exit 0) despite resolving the executable outside the install root. The negative characterization test failed as expected.
- **After patch:** `AssertNoReparsePoints` walks all existing ancestors of the target executable, current version pointer and previous version pointer, refusing reparse points before hashing or mutation.
- **Executed:** `python -m unittest tests.test_madar_update_contract tests.test_codex_upgrade_parity tests.test_release_restore_guard tests.test_release_persistence -q` under disposable `APPDATA`/`LOCALAPPDATA`. **20 passed, 0 failed, 0 errors**; `git diff --check` exited 0.
- A genuine real-user installer, Authenticode signature verification, and independent release acceptance were **not** performed.
