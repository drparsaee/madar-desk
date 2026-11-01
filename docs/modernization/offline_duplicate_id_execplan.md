# ExecPlan | Offline reconciliation duplicate-ID data-loss guard

## Purpose and boundaries
Continuation of Madar modernization, code source D:\CoS-Test\madar-desk, LocalForge main baseline 6f0da57ad40b59cc60a9db8347b391dd3ca2f995. Owner requires no silent loss of user edits. This pilot modifies only `offline_exchange.py` and `tests/test_offline_exchange.py`, with synthetic independent profiles. No changes to real app profile, Parsian accounting, committed financial ledger, installed binaries, or server ACL.

## Current behavior / source evidence
`three_way_merge` in `offline_exchange.py` calls `_three_way_items`, which calls `_index` on base, edited and server-latest record lists. `_index` builds a dictionary of ID to record without duplicate checks. Verified standalone red witness: base task with id=1 and edited tasks with two records with the same id 1, different titles, returns only the second edited record; the first disappears silently. This violates the no-data-loss requirement even if other host boundaries generally validate record IDs.

## Desired parity
1. Preserve existing byte-equivalent behavior and list ordering for valid unique-ID records; keep idempotent retries and concurrent unrelated merges.
2. Reject duplicates in any of the three task lists before attempting the merge, rather than selecting a winner. Admin project merges must get the same guard. Reject malformed record IDs/structure fail-closed rather than raising unexpected TypeError.
3. Never acknowledge or clear `OfflineStore.pending` when an invalid merge source is encountered. No host write or lost pending edits.
4. Existing host ACL still decides whether a user is permitted to edit; this source-only validation does not grant any permissions.

## Execution order and validation
1. Characterize existing tests with disposable APPDATA/LOCALAPPDATA/TEMP, including full Python suite launched first. Do not alter runtime while the full source baseline test is still underway.
2. Add regression showing duplicates are silently lost before change, and pending remains for conflict.
3. Apply minimal `_index` guard, run targeted tests, and neighbor LAN/bridge tests plus full Python/Node as applicable.
4. Record exact outcomes and test limitations; commit and push only after successful validations.

## Status / executed evidence
Baseline independent witness confirmed at SHA `6f0da57`, returning only the second duplicate. A new regression suite before the source change produced **5 assertion failures and 1 unexpected error** across 12 tests: duplicates in base/local/latest tasks and admin project lists silently collapsed; malformed list-valued ID produced TypeError instead of an explicit conflict. The original pending draft was never meant to be acknowledged in these cases.

After `_index` became a fail-closed duplicate/ID validator, 32/32 targeted offline tests passed. A new `tests.test_bridge_offline` case confirmed duplicate pending data is rejected before any host POST and remains in the pending store. The adjacent LAN/Bridge group passed **36/36**, and the full isolated Python regression run, before adding the safe test launcher, passed **168/168 modules / 1,612 tests**, including 2 skips and 2 expected failures but zero unexpected failures. The final protected `npm test` subsequently passed **169/169 Python modules / 1,617 tests** and **530/530 Node tests**, with a fresh Vite build. These are distinct test runs with overlapping cases, not additive totals.

## Limitations
Tests do not prove malicious users can bypass host validation. They demonstrate the merge helper's existing fail-open behavior when its input is corrupt or duplicated. No real two-computer or packaged EXE acceptance.
