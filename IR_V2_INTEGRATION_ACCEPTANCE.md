# Madar Desk — IR Journal V2 integration acceptance

Date: 2026-10-22. This is synthetic integration evidence, NOT production release approval.

## What actually exists

- Immutable IR RIAL journal, chart and money policies remain in ir_journal_v2.py, ir_chart_model.py, money_policy.py. Canonical RIAL integer amounts preserve single-RIAL precision.
- ir_journal_sqlite.py supports dedicated, opt-in RIAL SQLite storage with BEGIN IMMEDIATE, compare-and-swap revisions, append-only validation and duplicate business-source rejection. This separate store is NOT jointly crash-atomic with historical TOMAN finance.
- ir_accounting_host_v2.py provides an injected trusted-authority adapter for an ALREADY ISSUED, verified RIAL-only document; it strictly refuses legacy TOMAN-linked posting and is not exposed as a write endpoint in the current host.
- finance.py and ir_finance_v2_extension.py permit an optional, validated rialJournalV2 field in the existing finance domain. This allows opt-in RIAL snapshots to be committed inside the SAME existing UnifiedAppStorage finance revision. A PURE verified single-invoice composer exists but no live legacy invoice-issue adapter calls it yet.
- native_app.py now implements rialJournalRead(request) and rialJournalActivate(command), with corresponding admin-checked LAN methods. Read prefers V2 embedded finance data and otherwise reads an explicitly initialized dedicated RIAL SQLite file. It never reinterprets old TOMAN amounts as RIAL.
- POST /api/rial-journal/activate creates only a NEW EMPTY RIAL company/period after an admin explicitly requests it, on opt-in unified storage, and only if old finance history/card costs/accounting/purchase intake is absent. It never migrates user finance records. GET /api/rial-journal returns selected company/period with exact RIAL string amounts. Both are admin-only.
- src/App.jsx mounts a read-only RIAL V2 journal route with company/period inputs and an explicitly confirmed empty-activation form. Source TOMAN accounting UI remains separate and clearly labeled.
- app_storage.py protects already activated V2 data against legacy client downgrade/restore, journal rewrite, and unverified legacy-only invoice.issue. It does not issue legacy invoices in V2 itself.

## Local synthetic validation

No live APPDATA, Parsian, installed/running app, external database, Git or release was modified. All bridge and security stress tests use temp fixtures.

| Focused test family | Count | Result |
| --- | ---: | --- |
| accounting Python | 87 | PASS |
| finance Python | 28 | PASS |
| unified app storage Python | 30 | PASS |
| ir_* Python modules (including stress) | 99 | PASS |
| RIAL host read/activation/ACL Python | 10 | PASS |
| accounting workspace + RIAL panel Node | 32 | PASS |
| TOTAL | 286 | PASS, zero failures |

The final npm run build PASS completed with 1,644 Vite modules and a non-blocking bundle-size warning. No native EXE rebuild or GUI/UAT of a running EXE was performed.

Security tests cover 16 competing same-revision writers, 35 successful CAS retries, 8 same-source racing writers, cross-company and cross-project operations, malformed inputs, exact one RIAL, overflow, SQL quoted strings, direct snapshot tamper, rollback, close and reversal. See IR_JOURNAL_SECURITY_REPORT.md.

## Remaining safety gates

1. Existing accounting_service.py and finance.py workflows still issue TOMAN documents. The PURE co-commit composer is not yet called by a trusted single-SQL transaction invoice-issue host handler. V2 issuance/write operations are therefore deliberately unavailable through the UI/LAN.
2. A company-owned chart, party/detail mapping, account codes, project/task ownership and explicit tax/discount/advance recognition must be resolved from trusted host state before synthesizing invoice lines. No automatic posting is permitted from guessed account mappings.
3. Existing TOMAN finance history cannot be activated/migrated without verified unit and source manifests, opening entries, reconciled trial balances, dedupe, backup/restore drills and reviewed migration boundaries. New-company empty activation fails closed when legacy activity exists.
4. Standalone purchase bills, cost-derived purchases, treasury/check events, line-level tax treatment, authorized period close, reconciliation and full RIAL financial reporting are not yet integrated with the legacy host.
5. A direct raw SQLite writer with filesystem write privileges can recompute the journal hash chain and replace an internally valid history. The QA test intentionally reproduced this. Use independent signed/tamper-resistant hash anchoring and filesystem access controls before making stronger tamper claims.
6. Native EXE and end-to-end GUI/LAN failure-injection, simultaneous issue/period close, true cross-domain transaction, restart recovery and production deployment acceptance have not passed.

Decision: Legacy TOMAN accounting stays unchanged; RIAL V2 is opt-in, admin-restricted, and read-only for actual journals until the outstanding financial integrity and full integration gates are satisfied. Do not describe this as a completed, production-ready accounting migration or invoice integration.
