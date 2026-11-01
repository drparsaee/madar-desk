# ExecPlan | P0: verify offline full-recovery backup before publication

## Purpose and scope
Owner prioritizes preventing data loss in Madar before real-device user acceptance. This pilot fixes offline full recovery ZIP publication only. Baseline main SHA c91d3d647f9bf07f81647c2ae590481ef23aeff4. Files: full_recovery.py, tests/test_full_recovery.py, this plan. Synthetic paths and redirected APPDATA/LOCALAPPDATA/TEMP only; never real profiles, Parsian, installer, or live LAN.

## Existing behavior / overview
full_recovery.create_full_backup first stages task/collaboration/finance/identity/attachment files, validates source and computes SHA-256 inventory. It then writes a ZIP and fsyncs it, hard-links the temporary ZIP to the final filename and reports success. At this point, the ZIP is not read back or validated against the stored file digests. _extract_verified already implements the full readback/manifest/SHA-256/data-validation logic on restore.

## Planned design and parity
1. Confirm baseline: 11 tests in tests.test_full_recovery passed before modifications in disposable Windows environment.
2. Add a red regression: alter only staged synthetic tasks.json after _inventory calculates its digest; the current code publishes an unrestorable ZIP as successful.
3. Verify finished temporary ZIP with existing _extract_verified before link publication; require manifest bytes and count/size to match source inventory. On invalid ZIP, stop before publication and clean temporary files.
4. Preserve API shape, source bytes, no-clobber destination contract, offline precondition, full backup format, existing restore journal and rollback. No monetary conversion or data migration.

## Progress / surprises
Baseline verified: python -B -m unittest tests.test_full_recovery -q => 11 tests OK.
Red reproduction verified: the new test returned one failure before the fix: `RecoveryError not raised`, because the code had published an archive with a mismatched hash. The first green attempt found only an assertion-text mismatch (`Malformed manifest entry`); the final test changes content without changing UTF-8 byte size and requires the SHA-256 verifier to reject it.
After fix, targeted SHA-256 corruption case: 1/1 passed. `python -B -m unittest tests.test_full_recovery tests.test_automation_full_recovery tests.test_backup_scope_truth tests.test_release_restore_guard tests.test_host_backup_scheduler -q` returned **39 tests OK** with `PYTHONPATH` set to the repository `tests` directory and synthetic APPDATA/LOCALAPPDATA/TEMP. An earlier adjacent run without this import path encountered one `ModuleNotFoundError: test_data_model`; this was a test-runner invocation issue and was resolved before the 39/39 run. Existing source snapshots and untouched data are verified in tests.

## Validation and limits
Run focused and relevant recovery/backup tests in disposable profiles, py_compile and git diff --check. The readback gate requires additional temporary disk capacity and filesystem I/O approximately proportional to archive size. It cannot prove hardware power-loss durability, complete coverage of unrelated app data, live Parsian recovery or a deployed version. Git commit, push, installer and user acceptance are separate statuses.
