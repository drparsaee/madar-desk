# P0 purchase intake / supplier bill to RIAL V2: pure composer handoff

**Date:** 2026-10-22. **Status:** PURE COMPOSER IMPLEMENTED AND TESTED; **HOST INTEGRATION BLOCKED**. No real financial data, APPDATA, SQL/Parsian, UI, LAN server, EXE, Git or release was modified.

## Scope and recorded tests

Worker-10 created only three new files: ir_purchase_joint_issue.py, tests/test_ir_purchase_joint_issue.py and this IR_PURCHASE_JOINT_HANDOFF.md. Read-only analysis included accounting_service.py, purchase_intake.py, accounting_core.py, ir_journal_v2.py, ir_chart_model.py, money_policy.py, ir_finance_v2_extension.py, finance.py, native_app.py, lan.py, app_storage.py, ir_invoice_joint_issue.py and ir_journal_sqlite.py. No shared application source was edited.

Command: python -m unittest discover -s tests -p test_ir_purchase_joint_issue.py -v  
Result: **9 tests, 1.151 seconds, PASS (exit code 0)**.

Command: python -m unittest discover -s tests -p test_ir_finance_v2_extension.py -v  
Result: **6 tests, 0.100 seconds, PASS (exit code 0)**.

Command: python -m unittest discover -s tests -p test_rial_joint_issue.py -v  
Result: **10 tests, 0.800 seconds, PASS (exit code 0)**.

These three completed suites yielded **25 PASS, 0 FAIL**. The test fixture is purely synthetic; any SQLite tests use a disposable TemporaryDirectory inside the project and remove it afterward. There is no claim of EXE, GUI, network, multi-user concurrency or production test completion.

## What is implemented and directly checked

The exported function compose_purchase_issue_with_rial takes authoritative finance_before and reducer-issued finance_after, a narrowly scoped document.issue command, and host-derived actor, accounts, cards, projects, timestamp, expected finance SHA-256 and expected journal revision. It does no file or database IO. The function validates both finance states, reruns apply_madar_accounting with the supplied authoritative identity and original command, requires exact equality to the supplied finance_after, and verifies exactly one append-only old bill.issue event.

Only **one converted supplier intake** and its corresponding task/checklist bill are allowed. The intake must be priced with positive exact integer TOMAN unitPrice and quantity. The original named vendor must match the old registered party and the issued bill, its one expense line, supplier payable, project, card, checklist description, original price and quantity. The source index's fingerprint is reconstructed from the actual intake.convert recipe. Different bill IDs reusing the same card/checklist commercial source are rejected even when a second bill and index are individually schema-valid. Standalone purchase bills, multiple costs, tax, discount, purchase deposits and other non-intake sources intentionally fail closed.

The composer verifies the prior RIAL journal belongs to **one explicitly opted-in company**, has the exact expected revision, and has an eligible fiscal period for issue date. It creates immutable host-derived ChartSnapshot, VerifiedScopes, JobReference and JournalSource(kind=independent, source_id=billId) and appends **one** V2 entry: debit a temporary purchase expense leaf 500101 and credit a temporary supplier payable leaf 200101. Both sides equal original totalToman multiplied by 10 exactly as bounded integer RIAL. The payable line includes the named supplier party ID and the posting references bind to the project and task. Duplicate purchase-bill mirror sources fail closed. It serializes V2 through the existing strict journal serializer and returns a **deep copy of finance_after** with the journal embedded under the existing rialJournalV2 company.

The result includes candidate state, reducer result plus RIAL event metadata, and a sourceContract with named supplier, intake, bill, task, checklist, quantity, unitPriceToman, totals, project/company IDs, fiscal revision, finance before/after hashes, source fingerprint and attestation_sha256. This is **a plain deterministic SHA-256 audit digest**, NOT a digital signature, authentication credential or authorization. Actor, roles, company mapping, snapshots and clock MUST be supplied from the trusted host while holding its finance lock. The pure Python function cannot prove its caller is a legitimate host.

## Verified focused scenarios

| Scenario | Result |
|---|---|
| One converted, reviewed, issued purchase of 7 units at 120 TOMAN | **PASS**: one 8,400 RIAL debit, one 8,400 RIAL credit, named vendor and bill provenance retained, prior and reducer outputs not mutated |
| Intake missing price or bill not approved | **PASS**: rejected without posting |
| Forged actor, company/project/card, vendor/source fingerprint, unit price, source link | **PASS**: refused |
| Old snapshot finance hash, RIAL revision, future time, malformed intent, extra financial changes | **PASS**: refused |
| Same bill issued again or different event ID | **PASS**: refused; no second mirror |
| Another legitimate old bill indexed to the same commercial card/checklist source | **PASS**: rejected even if generic finance validator accepts its link |
| Float price, unbounded integer ×10, multiple companies, period excluding issue date | **PASS**: rejected |
| Attempt to commit the valid purchase+V2 finance candidate via existing SQLite CAS | **PASS proving blocker**: rejected, previous revision untouched |
| Attempt to commit even the FIRST intake.create after RIAL activation via existing SQLite CAS | **PASS proving blocker**: rejected, previous revision untouched |

## Blocking changes for Prime, not performed in this slice

**P0 blocker 1: Intake cannot start in an activated finance host.** The current ir_finance_v2_extension._preserve_issued_history refuses ANY mutation in accounting, accountingSources or purchaseIntakes. It runs from app_storage._protect_rial_finance_history under the unified SQLite transaction, and the new test reproduces rejection for even a legitimate intake.create with zero payable. Prime needs a precise host-side permission and transition policy for intake.create/price/convert/review while preserving existing journal/source immutability and preventing false liability.

**P0 blocker 2: Old bill.issue and RIAL are not jointly recognized by persistence.** The current app_storage._protect_rial_finance_history matches one new legacy finance.ledger invoice.issue to one V2 event. Purchase instead appends to finance.accounting.events, without a new legacy finance.ledger sale entry. It must compare one verified old bill.issue event, original supplier and source, TOMAN posting and one matched RIAL journal inside the same revision CAS. Simply skipping _preserve_issued_history or permitting arbitrary accounting events would create an unsafe bypass.

**P0 blocker 3: Native and LAN accounting commands do not call this purchase composer.** Currently both paths call apply_madar_accounting directly for document.issue. An eventual integration must acquire authenticated host identity and current finance head under lock, generate the verified old reducer result, invoke the composer, then CAS-commit its WHOLE finance snapshot once. No separate old accounting commit or second RIAL database transaction is permitted. Support idempotent retry after committed issue by checking the exact old event and RIAL source; this pure function currently rejects replay as a new issue.

**P0 blocker 4: Company ownership and actual Iranian chart are not established.** The fixed 500101/200101 chart is an isolated temporary shadow chart, not a validated company KOL/MOEIN/TAFSILI account registry. One-company-only behavior prevents guessing ownership when multiple companies exist; production needs an authoritative company/project/vendor mapping and versioned chart verification before enabling real financial postings.

Unsupported until distinct reviewed bridges: purchases assembled from multiple cost sources, general standalone bills, tax and discount, advance payments, reversals, treasury settlement, historical migration and GUI invoice previews.

### Exact suggested host source contract

The trusted host must bind these values to the same finance snapshot under lock and CAS: financeBeforeSHA256, companyId, projectId, cardId, stepId, intakeId, billId, supplierId, supplierName, quantity, originalUnitPriceToman, totalToman, totalRial, approvedBillIssueEventId, mirrorRialEventId, priorJournalRevision, reducerAfterSHA256. Verify them against authoritative task/checklist, vendor registry, intake record, source index, original accounting ledger and posted RIAL chart evidence **at the persistence boundary**. A hash of the tuple alone is not a signature and does not establish permission.

**Release readiness: BLOCKED.** The pure candidate is meaningful and reproducibly tested; the live activated host currently rejects both its initial intake mutation and final purchase+RIAL mutation. Do not claim hosted, LAN, GUI or packaged integration until the shared guard and host routing are updated and independently retested.
