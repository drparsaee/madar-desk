# Madar / Taraz P0 manual connection: source contract and installed UI gap

Date: 2026-11-10. Scope: manual nonfinancial proposal, review/rejection, and
readback for a saved Madar card. Radar is deferred. No financial posting.

## Verified current source behavior

The source App.jsx requires explicit per-user consent, an available
proposal-only inbox, edit permission, and a completed card save. It calls
Bridge.tarazIntegrationPrepare(taskId) **before**
Bridge.tarazIntegrationQueue(taskId, null, stableId); a retry uses the old
ID. The task editor explicitly calls Bridge.tarazIntegrationHistory(task.id,
true) for scoped local observations. The Python bridge checks client role
and project grants and refuses offline, duplicate, unprepared, changed,
and conflicting requests. History remains local-file observation with
peerVerified=false, never an official financial receipt.

New test: py -3.12 -B -m unittest tests.test_mtr_taraz_connection_contract_20261110 -v

Observed: **6 tests, OK**. Actual current source Bridge methods were invoked
against disposable synthetic requests. The test also calls the actual
detached Taraz source's review_request for both reviewed/rejected decisions
and checks scoped Bridge history. It checks stable IDs and no duplicate
publication, stale/unknown ID denial, conflicting paths, tampered receipt
remaining unknown, offline refusal, client role/project grants, and UI
consent/prepare/queue ordering. The in-memory client identity is a
synthetic fixture: this is not verification of real host authentication.

Neighbor tests plus this regression:

py -3.12 -B -m unittest tests.test_taraz_exchange tests.test_taraz_manual_retry tests.test_taraz_review_status tests.test_mtr_e2_send_journal tests.test_mtr_taraz_connection_contract_20261110 -q

Observed: **39 tests, OK**.

## Installed v1.0.26 method mismatch: P0 blocker

A read-only PyInstaller code-object inventory of installed Madar
MadarDesk/versions/1.0.26/Madar-Desk.exe independently returned:

| Native Bridge method | Current source | Installed 1.0.26 |
| --- | --- | --- |
| tarazIntegrationStatus | Present | Present |
| tarazIntegrationPrepare | Present | **Absent** |
| tarazIntegrationQueue | Present | Present |
| tarazIntegrationHistory | Present | **Absent** |

Installed v1.0.26 is **incompatible with the current Prepare → Queue →
History UI contract**. Its prior metadata-only queue operation exists, but
durable preparation and card-specific manual status readback are not
packaged. This independently matches the earlier report in
MTR_INSTALLED_LOCAL_BRIDGE_PROOF_20261110.md.

The existing shipped-binary synthetic inspection script was rerun:

py -3.12 -B scripts/qa_installed_madar_taraz_bridge_20261110.py

Observed exit 0, installedExecutableHashesMatched=true,
packagedNativeBridgeMethodsExercised=true, shippedBackendsConnected=true,
manualReviewAndRejection=[reviewed,rejected], ledgerPosted=false,
realProfileAccessed=false, uiOrNetworkTested=false.
It invokes selected packaged methods with synthetic objects and a
disposable inbox. It does not operate installed GUIs, verify actual
authentication or touch the live accounting book. Prior installed GUI
smoke mounted the Madar UI, but did not prove task editor/send control
interaction.

## Remaining acceptance / action for prime

1. **P0:** Integrate and package matching current Madar frontend and Bridge
   methods. Verify packaged UI asset names, exported bridge surface, and
   method signatures in the new artifact. Keep packaging/deployment gates.
2. **P0:** On a disposable, expressly authorized nonfinancial test card,
   confirm the installed manual path: consent → saved-card send → Taraz
   inbox manual review/rejection → Madar scoped history refresh. Exercise
   unavailable/unknown cases. Do not inject requests into real inbox.
3. **P0:** Independently validate actual signed-in user and project grants.
   The current local handoff operates only for the same Windows user on
   the same computer.
4. **Future:** Official Taraz finance/catalog/identity/receipt authority
   and authenticated cross-device LAN remain unverified. A local review
   marker is not accounting approval or ledger posting.

No real profiles, network, running application, installer, operational
finance data, commit, push, or deployment were modified by this worker.
