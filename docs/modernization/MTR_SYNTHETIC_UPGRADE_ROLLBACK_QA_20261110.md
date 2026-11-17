# MTR P0: Synthetic upgrade to exact-checkpoint rollback dry-run

**QA ONLY, NOT A RELEASE OR INSTALLER.** The drill opens neither installed
Madar/Taraz executables nor real profiles, accounting data, LAN or services.
Everything changed resides in one fresh disposable 3-database temporary
root, removed at exit. No existing application source file is edited.
Policy is **UNSIGNED_QA_ONLY**; the release decision remains **NO_GO**
regardless of a passing synthetic test. Installation permission is always
false.

## Run

    python -B scripts/qa_mtr_synthetic_upgrade_rollback_20261110.py
    python -B -m unittest -v tests.test_mtr_synthetic_upgrade_rollback_20261110

## Pinned, non-release source artifacts

Preflight verifies the exact SHA-256 of both QA executable images, build
reports, Madar source inventory/provenance, source package versions and the
Taraz peer registry source. Neither executable is launched.

| QA source | Executable SHA-256 | Source snapshot SHA-256 | Snapshot app version |
|---|---|---|---|
| Madar | 11a9726f976bd633c6eb120b939e1d7aab63c6ca99a3e3b5a5cc57bd967ed4f9 | f1fcade603d985d7755990422748b6b83428343c6de6e60e869b651afa3c8c18 | 1.0.23 |
| Taraz | f3c4d65418d8f9d80a40618c01bb1534841ca18bf863fd9d09d5ca0fb8449662 | cedd3c8cc51802afe0270cbd08971a1f67347ed3a269d7ec5908fe4c62b6f0cc | 1.0.0 |

These hashes are integrity pins, **not publisher signatures**. The Taraz
source snapshot hash is bound to the pinned build report, and the specific
peer registry source bytes are independently hashed; the script does not
rehash all 120 Taraz build inputs. The 6501-entry Madar source manifest tree
digest is recomputed. Both QA artifacts are explicitly NONRELEASE and
cannot be interpreted as installed-version or release acceptance. The Madar
QA version 1.0.23 is older than the previously observed installed 1.0.26,
so it is **not** a valid actual installation upgrade candidate.

## Synthetic rollback sequence

1. Create a new temp-root metadata HostRequestStore, OneShotDispatchGate and
   isolated TarazPeerRegistry. Persist a manually authorized synthetic host
   request, irrevocably consume a first-dispatch slot, mark the attempt
   unknown, and record an in-process synthetic HMAC peer intake/query. No
   real TLS or network transmission.
2. Call the existing three-database backup helper in read-only code mode.
   It uses native create-only SQLite backup/archive APIs and disables all
   first-dispatch permits in the backup. Verify full file SHA-256, SQLite
   integrity and foreign keys, schema, peer immutability triggers, complete
   row digests and manifest SHA-256 before any simulated upgrade.
3. Create a bounded local synthetic upgrade plan, check its version/source
   identity and reparse it from its newly created file under hash. Create a
   second synthetic request, consumed dispatch slot and peer query on the
   *temporary live* databases. All three live DBs must diverge from their
   original snapshots.
4. Validate the entire immutable checkpoint again *before* making any
   rollback destinations. Copy each original backup byte-for-byte into a
   separately created temp rollback directory using fsync and atomic
   create-if-absent, never in-place overwrite. Verify restored **exact file
   SHA-256**, row-content hashes, independent SQLite/foreign-key checks,
   version, schema and peer immutability triggers.
5. Open the restored stores with actual source classes and demonstrate the
   original unknown-after-attempt slot remains query-first/no auto replay.
   Both a previously consumed slot and a slot consumed during simulated
   upgrade are denied first-dispatch permits. Original peer request and
   query bindings remain replay-idempotent. Rehash all rollback DBs again
   after the checks and demand exact original snapshot bytes.

Negative tests deny corrupted or changed-but-valid SQLite backups, missing
files, duplicate/extra backups, symlinked sources/targets, pre-existing
rollback destinations, forged QA report pins, unknown source/app version,
untrusted plan actions and duplicate JSON plan keys.

## Unclosed production gates

**Not proven:** coordinated/atomic cross-database backup epoch, concurrent
writers, genuine power loss, real process/service restart, real application
version migration/installer, official TLS peer identity, private-secret
re-provisioning, signed publisher/release provenance, production ledger
receipt, full real profile/attachments restore or production rollback.
The synthetic upgrade plan checksum is not a signed trust anchor. Output
never authorizes installation, deployment or financial replay.

Prime additionally reported a current cross-application identity blocker:
Madar actor ID (approximately 77 characters) cannot be equated directly
with the Taraz local username (maximum 40 characters). This report is
**not independently verified in this rollback drill**; no actor-binding
or official financial authority is therefore claimed. Owner/prime must
resolve and verify this boundary separately before release.
