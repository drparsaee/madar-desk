# CURRENT Madar Desk purchase/RIAL host security audit

**Date:** 2026-10-22. **Result:** current host integration is active in synthetic tests. The earlier handoff claiming that all purchase activity is blocked is **STALE**. One **internal persistence-level provenance defect** is reproducible; no user-facing exploit has been demonstrated.

## Files and test isolation

This worker created only NEW tests/test_purchase_host_adversarial.py and NEW CURRENT_PURCHASE_HOST_AUDIT_20261022.md. No shared source, original composer, release, Git, APPDATA, production SQL or Parsian files were modified.

The tests use the already existing isolated native Bridge fixture. APPDATA, LOCALAPPDATA and native_app.datadir are all patched to a TemporaryDirectory before constructing the Bridge; SQL writes occur only inside that fixture. LAN users/tokens are synthetic; no HTTP listener or network server was started. Cleanup is registered by the fixture.

## Actual source state, not the old handoff

- native_app.py:1497-1525 routes active RIAL document.issue through ir_purchase_host_adapter.issue_supplier_purchase_with_rial; it commits the complete finance domain with expected finance SHA-256 and SQLite revision CAS.
- lan.py:671-693 uses the same verified adapter in the authenticated service path.
- app_storage.py:89-150 invokes ir_accounting_transition_guard.inspect_accounting_transition and verifies one old accounting bill.issue with the matching purchase RIAL journal in the same SQLite transaction. The guard also permits nonposting purchase intake/accounting staging.
- The original ir_purchase_joint_issue.py is not reimplemented or modified.

## Executed tests (latest complete runs)

| Suite | Observed result |
|---|---|
| test_rial_purchase_host_integration.py | 2/2 PASS, 0.799s |
| test_ir_purchase_joint_issue.py | 9/9 PASS, 1.152s |
| test_rial_joint_issue.py | 10/10 PASS, 0.845s |
| **NEW test_purchase_host_adversarial.py** | **8/8 executable assertions PASS**, 4.728s, exit 0 |

**Total: 29 successful executable assertions.** WARNING: the last suite includes a **deliberate characterization that confirms a broken security invariant**. Eight green test results do not imply eight secure boundaries.

## Adversarial case outcomes

| Attempt | Observed outcome / security interpretation |
|---|---|
| Legitimate 7 × 123 TOMAN supplier bill | **PASS:** one joint SQLite revision stores old payable 861 TOMAN and balanced 8,610 RIAL V2 entry. Exact retry no-op. |
| Edit price, vendor name or vendor ID on already converted intake | **PASS:** current SQLite guard refuses all three without head revision change. |
| Inject vendor, actor or scopes into native intake.price command | **PASS:** normal reducer refuses unknown fields, no persistence. |
| Reissue same bill under different event ID | **PASS:** native path refuses, existing event does not post twice. |
| Commit legacy bill.issue without V2 mirror | **PASS:** storage guard rejects unpaired purchase. |
| Commit with stale finance SHA or stale integer SQLite revision | **PASS:** both preconditions refuse overwrite after an intervening valid party.register. |
| Inject OSError after SQLite revision INSERT and head UPDATE, before COMMIT | **PASS:** old and V2 remain unchanged after rollback; subsequent legitimate issue succeeds once. Actual power failure not simulated. |
| LAN editor with added financeEdit, fake token, client-supplied actor/company/proof | **PASS:** service method rejects them; authenticated LAN admin issues and replays correctly. No actual HTTP/TLS request tested. |
| Direct internal storage price rewrite plus fake intake receipt | **FAIL SECURITY INVARIANT:** storage accepts an altered priced-intake unitPrice without valid authoritative intake.price event. |

## Confirmed defect: price provenance of OPEN PRICED intake can be rewritten through an internal storage commit

**Affected code:** ir_accounting_transition_guard.py:43-80, especially 60-75. The guard freezes the original supplier/project/card/step/quantity and all *old* receipt values, but permits the price of an intake whose status is already priced to change while remaining priced. If any new receipt **key** appears, the guard permits the mutation without proving that the receipt corresponds to an authentic reducer-issued intake.price event. purchase_intake.validate_intakes only checks the receipt shape and 64-hex fingerprint format, not receipt replay.

**Exact synthetic reproduction (executed in NEW test):**

1. In temporary Bridge + unified SQLite, activate a single empty RIAL company and submit legitimate intake.create for intake-open, quantity 2 and synthetic vendor/card/step.
2. Submit legitimate intake.price for intake-open with integer unitPrice **123 TOMAN**.
3. Load the current SQLite head. Deep-copy its finance state. Set its purchaseIntakes.records.intake-open.unitPrice to **999** without calling the reducer.
4. Append purchaseIntakes.receipts.injected = {fingerprint: 64 zero hexadecimal characters, result: {proposedTotal: 1998}}. There is **no legitimate event** corresponding to the forged price change.
5. Pass the modified whole finance bundle to UnifiedAppStorage.commit with the correct expected integer revision. **Commit succeeds** and the new database head contains the forged **999** price.

The exact steps are in test_persisted_priced_intake_can_be_rewritten_with_forged_receipt. This test is intentionally written to assert and document the **currently observed vulnerability** so it stays green as a characterization, not to certify the behavior. After a fix it should be inverted into an expected-rejection regression test.

**Threat model restriction:** This test requires a caller of the internal whole-bundle UnifiedAppStorage.commit API. It does **NOT** prove that a non-admin LAN client, a WebView user or a remote attacker can send that forged finance bundle to the service. The tested native/LAN commands authenticate the actor and call trusted reducers. This is a real **storage boundary integrity defect**, not an established remote privilege escalation.

**Recommended fix for Prime:** Require exact replay/binding of each newly appended intake receipt to the previous intake snapshot and the allowed issuer command/transition. A new syntactically valid receipt key cannot be sufficient. Verify the after-intake state equals the result of applying the corresponding validated intake.create/price/cancel command; handle intake.convert only when its linked original bill.create is properly reconciled. Keep the guard under the existing SQLite CAS. Add an expected-raise regression using steps 1-5, then rerun native/LAN and sale/purchase tests. Do **not** broadly allow arbitrary finance mutations or disable the purchase paired-V2 reconciliation.

## Limits and next verification

- Single activated company and fixed shadow expense/payables chart remain intentional restrictions. No real company/project/party registry, multi-company accounting, production chart configuration or migration were verified.
- The LAN tests call service methods directly, not HTTP over TLS. No EXE or GUI/WebView security automation; no live APPDATA, SQL/Parsian data, multi-process concurrency or physical power-cut crash recovery was exercised.
- The server-side purchase adapter is now present. The old claim of an unintegrated host is invalid; remaining risk is **verified source/receipt provenance inside the storage transition guard** and the untested external boundaries.
- Prime was notified of this confirmed defect and exact steps **before any shared host source edit**. This worker made no shared source edits.
