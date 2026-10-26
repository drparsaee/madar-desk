# Madar Desk and Independent Accounting Profile

This is an **adoption template**, not an assertion that rules are already installed in the Madar Desk repository.

## Data invariants

- Keep accounting as an independent workspace with explicit links to cards and checklist steps; no implicit cross-workspace financial posting.
- Preserve stable source identifiers and record provenance for every imported historical item.
- Distinguish invoice draft, confirmed posting, payment, cheque, ledger and financial reporting states.
- Do not guess whether an imported monetary amount is in IRR or toman. Quarantine ambiguous units until resolved by evidence/owner decision.
- Do not write to a live Parsian database or restore a production SQL backup for testing. Use isolated disposable database copies, record counts and verification evidence.
- Financial migration requires coverage for parties, inventory, invoices, treasury, cheques and GL, plus reconciliation and rollback before a completion claim.
- Keep Windows-first RTL/Jalali/Gregorian support and existing LAN/offline/recovery behavior. A sync conflict must not silently overwrite financial truth.

## Safe implementation

Inspect existing React and backend schemas before changing them. For a focused defect, keep affected components and tests small. Validate permissions, idempotency, total invariants, and backup/recovery when relevant; distinguish mocked migration coverage from real historical transfer.

Any change to real user data, installed program, SQL services, backups or published installers requires separately evidenced safeguards.
