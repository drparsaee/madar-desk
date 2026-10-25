# Madar RIAL host security and atomicity review

**Date:** 2026-10-22. **Outcome:** 12/12 new focused synthetic hostile tests PASS, plus 8/8 existing joint-issue tests and 6/6 extension tests PASS in separate runs. **This is not a production security certification.**

## Scope

Only two NEW files owned by worker-10: tests/test_rial_host_security_invariants.py and this review. No native_app.py, lan.py, app_storage.py, finance.py, Git, APPDATA, real SQL/Parsian, installed EXE or global application files were edited. All database writes were directed to unittest TemporaryDirectory under the Madar repository, using disposable SQLite snapshots. A native Bridge was constructed without running its APPDATA-opening initializer, then bound to this temporary store. LAN methods used synthetic local accounts and sessions, without starting an HTTP server or attaching to an existing user service.

Read-only inspection covered native_app.py, lan.py, app_storage.py, ir_finance_v2_extension.py, ir_journal_v2.py, finance.py and relevant referenced contracts in ir_invoice_joint_issue.py / ir_journal_sqlite.py. Other workers modified shared host source during these tests, so the assessment below describes the **last fully completed passing runs**, not earlier partial runs.

### Actual commands and results

- python -m unittest discover -s tests -p test_rial_host_security_invariants.py -v: **12 tests, 10.758 s, OK, exit 0**
- python -m unittest discover -s tests -p test_rial_joint_issue.py -v: **8 tests, 0.645 s, OK, exit 0**
- python -m unittest discover -s tests -p test_ir_finance_v2_extension.py -v: **6 tests, 0.101 s, OK, exit 0**

## Hostile scenarios

| Scenario | Result | Actual exercised behavior |
|---|---|---|
| Old complete bundle attempts to remove RIAL journal | **PASS: rejected** | UnifiedAppStorage.commit and restore reject historic four-domain finance snapshot after V2 activation; SQL head unchanged; stale expected revision also conflicts. |
| Old task-only LAN client snapshot after activation | **PASS: preserved** | Direct authenticated LanService.write_state kept RIAL finance unchanged. SQL integrity_check true. No real HTTP request was performed. |
| Activate RIAL over legacy TOMAN history | **PASS: rejected** | A valid existing contract.set made native activation raise; no V2 company was silently created or previous SQL revision replaced. |
| Forged cross-company posting line or foreign project/task | **PASS: rejected** | Immutable journal posting refuses foreign line company, unverified source project and missing VerifiedScopes; no storage write. The scopes supplied by the test were synthetic trusted fixture objects. |
| Duplicate commercial source with a different event ID | **PASS: rejected at serialization** | Pure journal post_journal can assemble a second event ID. V2 journal serialization enforces business source uniqueness and raises JournalV2Conflict before the SQL store accepts it. |
| SQL failure after revision INSERT and head UPDATE | **PASS: rolled back** | Injected OSError inside _insert after both writes and before COMMIT left all domains, head and historic revisions identical. SQLite integrity_check true. This is a controlled exception, not a real power-cut test. |
| Shared-domain stale finance CAS | **PASS: rejected** | An intervening finance edit invalidated expected_finance_sha256; replay of an earlier composed finance/RIAL candidate raised CONFLICT without overwriting the new finance state. |
| Legacy-only invoice.issue after RIAL activation | **PASS: rejected** | V1 issue result without matching RIAL posting fails at the unified storage guard; no partial commit. |
| Valid legacy TOMAN and RIAL posting composed together | **PASS: committed** | One synthetic SQL revision contains a legacy issued invoice ledger item and matching balanced 1,200 RIAL journal, with integrity check. |
| Native host invoice.issue and repeated identical event | **PASS: once and exact replay** | Bridge.financeCommand uses the current verified joint-issue host adapter. Both sides persist together in one SQL revision; replay returns the same RIAL event metadata without revision advancement; a different event ID for already-issued invoice is refused. |
| LAN grant bypass | **PASS: rejected** | An editor, even with an artificially assigned financeEdit flag, cannot activate/read RIAL; invalid bearer token is refused by LanService. HTTP transport, TLS and real profiles were not exercised. |
| Supplier purchase intake with no price | **PASS: unbooked** | Bridge.accountingCommand intake.create gave status unpriced and bookedPayable=0; intake.convert refused; read view showed no purchase document and zero supplier payable. This exercises backend, not GUI clicks. |
| Unverified invoice preview request | **PASS: fail closed, feature absent** | Native RIAL read accepts only companyId/fiscalPeriodId; previewOnly/invoiceKind/invoiceId request is rejected and no financial event is generated. Actual UI behavior is not established. |

## Known limitations and concrete blockers for Prime

**P0 integration gap: purchase to RIAL accounting.** The active joint-issue adapter covers the existing **sales** invoice.issue only. Unpriced supplier intake is correctly prevented from creating payable balances, but price -> purchase bill -> review -> issue -> balanced RIAL GL is not covered by this adapter. This needs an independently verified purchase posting contract and shared CAS.

**P0 integration gap: company/project authority and real Iranian chart.** The current sales adapter builds a restrictive fixed **shadow** chart for its own synthetic issue and binds all legacy sales to the single opted-in company. This review did not establish an authoritative company-to-project registry or trustable production KOL/MOEIN/TAFSILI mappings. The authenticated administrator chooses a company ID on activation; that alone is not independent proof of business-company membership. Multi-company correctness remains unverified.

**GUI invoice preview gap confirmed at host method boundary.** Native RIAL read rejects an invoice-preview DTO with invoiceId, invoiceKind and previewOnly. If the current interface tries to use that method for preview, the request cannot succeed. This should be wired to a separately authorized read-only preview service or disabled until implemented. Unpriced purchase behavior was verified at the backend; a real WebView GUI flow was not executed.

**Not tested:** Browser/WebView or EXE, actual LAN HTTP/TLS requests, concurrent independent Windows processes, true crash or power-loss durability, loaded user ACL/permissions, real data migration, multi-company access isolation, money overflow on every edge, general ledger reports and downstream treasury payment/cancel/reversal paths. Storage currently fails closed for unsupported post-activation treasury mutations, a functional limitation rather than evidence of an authorization bypass. Default LAN HTTP is possible in code; TLS confidentiality was not tested.

## Security interpretation and intermediate observations

The final 12 focused assertions exercised real Python methods and temporary SQLite commits. They do **not** establish runtime security merely because assertions exist: executable validation evidence is the completed unittest output. No P0 bypass was reproduced in the tested scope. The remaining blockers are **integration completeness and evidence**, with the purchase-to-RIAL issue path and company/project ownership contract foremost.

During the work, early runs failed because the synthetic Bridge intentionally bypassed its initializer and lacked harmless path attributes; the fixture was corrected without changing host source. Concurrent workers then added paired TOMAN/RIAL storage and native issue routing; earlier assumptions that a valid pair would be rejected ceased to be true. There was an interim repeated-issue mismatch: the new journal source changed to an independent invoice ID while its replay matcher still expected a task source, briefly rejecting replay. The currently read code has the matching independent-invoice check and the last full suite shows exact replay success. These intermediate failures are **not asserted as current defects**.

**Prime handoff:** preserve the host-owned provenance, strict V2 serialization/source uniqueness, and one-domain SQLite CAS guards. Complete and separately test verified purchase posting, real company/project chart binding and GUI preview, then run native EXE, authenticated LAN and crash-recovery QA before declaring production readiness.
