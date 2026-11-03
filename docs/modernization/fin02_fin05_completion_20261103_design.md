# FIN-02 / FIN-05 bounded financial design and invariants

## New receipt command

`inventory.receive` accepts its existing fields, plus for a discounted bill:

```json
{
  "type": "inventory.receive",
  "eventId": "receipt-001",
  "warehouseId": "WH1",
  "itemId": "A",
  "quantity": 2,
  "postingDate": "2026-10-03",
  "billId": "supplier-bill-001",
  "taxTreatment": "expense",
  "discountAllocation": "per-line-exact",
  "lineDiscounts": [
    {"lineIndex": 0, "amount": 1},
    {"lineIndex": 1, "amount": 3},
    {"lineIndex": 2, "amount": 6}
  ],
  "allocationReference": "supplier-evidence-001",
  "allocationReason": "Accounting-approved line-level supplier discount"
}
```

The command refers to a previously posted bill. `lineDiscounts` must contain exactly all line indexes, in order, with nonnegative bounded exact integers and `sum(amount) == bill.discount`. Each line amount cannot exceed its original gross. The operator-entered reference is a trace label, not a fetched or certified supplier document. Only a trusted admin actor may establish the policy, and all later receipts of the same bill use the exact same allocation, reference and reason. The original issued bill posting, total, payable and invoice metadata do not change. No client-chosen chart account or exchange rate is accepted.

`taxTreatment='expense'` must be explicit when bill tax is nonzero. System-account routing checks require original source expense account, inventory asset 1300, COGS 5300, purchase discount 5100 when discounted, and purchase tax expense 5200 when taxed. VAT remains an expense under the existing accounting convention. Requests to treat tax as recoverable, or to redirect posted tax to an unverified asset, are rejected.

## Exact FIFO and reversals

For purchased line unit price `p`, original quantity `Q`, line allocation `d`, prior returned units `r`, define effective remaining quantity `q = Q-r` and effective remaining discount `d' = d - round_half_up(d*r/Q)`. The total remaining gross less discount is `N=q*p-d'`. Require `q>0`, all unit costs strictly positive, and `N` within original bill limits. Let `b, m = divmod(N, q)`. The first `m` canonical units have value `b+1`; the rest have value `b`. Partial receipts consume consecutive canonical units by previously received nonreversed quantity, with at most two FIFO layers per receipt. Therefore summing all receipts always produces exactly `N`, regardless of partial quantities or warehouse, and no floats/implicit VAT amounts are introduced.

Each new receipt has a reserved internal FIFO source `@receipt:<eventId>` to distinguish it from historical receipt layers labelled with `billId`. Reversing its movement first checks quantity and value of the matching source layers, then removes those units, debits/credits the exact opposite of the previously posted GL lines and preserves the original journal. Subsequent item movements must be reversed first. Historical `single-line-uniform` commands use their original source/cost logic and remain replayable.

The GL reclassification per receipt is `Dr Inventory 1300 = N_received`, `Dr Purchase discounts 5100 = d_received`, `Cr source purchase-expense account = gross_received`. An item discount affects its own unit values only. Service-line discounts remain posted in 5100 and retain their original document meaning. `bill.return` after prior stock reversals uses cumulative per-line `round_half_up(allocated_discount * returned_qty / original_qty)` differences. Untaxed partial credit notes and taxed **full-document** credit notes are supported. A taxed partial credit note in the new allocation mode fails closed because the document stores no source-proven per-line tax amounts. Legacy return behavior remains unchanged.

## Mandatory fail-closed constraints

Unapproved account schema, duplicate item IDs within a bill, unallocated or undocumented discounts, policy changes after first stock receipt, historical prior credit notes before first new-mode allocation, stock quantity over net unreturned original quantity, nonpositive unit costs, customer-less/journal-less postings, and unsupported tax treatment all reject atomically. The feature does not assert that the supplier line allocation is legally or commercially correct; an authorized accountant must confirm the documentary evidence.

## FIN-05: prerequisites for a separate VAT implementation

No source-backed recoverable-input-VAT entitlement or effective tax policy has been supplied, so this branch **does not implement VAT reclassification**. Before enabling it, require: dated authorized tax source and company status/eligibility; specific supplier invoice status and eligible item groups; allocation of recoverable/nonrecoverable tax by line; approved asset account and posted expense account mapping with historical custom-system account migration; administrator-only change with reason and source citation; controlled debit to eligible input-VAT asset versus credit to 5200, never double-claiming; a linked reversing journal and credit-note/return reductions; closed-period protection, idempotency, GL tax trial balance and statutory reconciliation. This is a design prerequisite, not a statement of tax law or a live entitlement.
