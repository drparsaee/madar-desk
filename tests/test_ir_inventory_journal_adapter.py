"""Synthetic domain security/precision tests for FIFO -> RIAL V2 journal bridge."""
from dataclasses import replace
import unittest

from ir_chart_model import (
    ChartAccount, ChartSnapshot, CostCenter, JobReference, FloatingDetail,
    PartyDetailLink, DetailBinding,
)
from ir_inventory_rial import (
    BusinessSource, ItemSpec, InventoryAccountMapping, StockAuthority,
    StockEvent, append_stock_event, new_inventory_state,
)
from ir_inventory_journal_adapter import (
    InventoryBridgeConflict, InventoryBridgeError, VerifiedGLPosting,
    VerifiedInventoryAccounts, VerifiedReceiptSettlement, apply_inventory_gl,
)
from ir_inventory_journal_adapter import _journal_id
from ir_journal_v2 import (
    FiscalPeriod, JournalLine, JournalSource, PostingReference, VerifiedScopes,
    PostedJournal, new_journal_state, post_journal, replay_journal,
    close_fiscal_period,
)
from money_policy import CompanyMoneyPolicy


def fixture_chart(company="co1", *, freeze_inventory=False):
    accounts = []
    for code, kind, leaves in (
            ("10", "asset", (("100101", "Inventory"), ("100102", "WIP"))),
            ("20", "liability", (("200101", "GRNI"), ("200102", "AP"),
                                  ("200103", "Price GRNI"))),
            ("50", "expense", (("500101", "COGS"), ("500102", "Shrinkage"))),
            ("70", "revenue", (("700101", "Count gains"),))):
        accounts.append(ChartAccount(company, code, "KOL", None, "Group " + code, kind))
        parent = code + "01"
        accounts.append(ChartAccount(company, parent, "MOEIN", code,
                                     "Parent " + parent, kind))
        for leaf, title in leaves:
            accounts.append(ChartAccount(
                company, leaf, "TAFSILI", parent, title, kind,
                accountable=True, frozen=freeze_inventory and leaf == "100101"))
    return ChartSnapshot(
        company, accounts=tuple(accounts),
        details=(FloatingDetail(company, "FD-000001", "Vendor 1", "PARTY"),),
        party_links=(PartyDetailLink(company, "vendor1", "FD-000001"),),
        bindings=(DetailBinding(company, "200102", "FD-000001"),),
        project_ids=("p",),
        cost_centers=(CostCenter(company, "CC-0001", "p", "Job cost center"),),
        jobs=(JobReference(company, "job1", "p", "task1", "CC-0001"),),
    )


class InventoryGLAdapterTests(unittest.TestCase):
    def setUp(self):
        self.stock = new_inventory_state(
            "co1", (ItemSpec("co1", "sku1", "kg", 1000),), ("wh1", "wh2"))
        self.journal = new_journal_state("co1", (
            FiscalPeriod("co1", "P", "2026-01-01", "2026-12-31"),
            FiscalPeriod("co1", "P2", "2027-01-01", "2027-12-31"),
        ))
        self.base = InventoryAccountMapping(
            "co1", "100101", "200101", "500101", "700101", "500102", "200103")
        self.map = VerifiedInventoryAccounts(self.base, "200102", "100102")
        self.chart = fixture_chart()
        self.policy = CompanyMoneyPolicy("co1")

    def movement(self, kind, eid, qty, *, source=None, **fields):
        payload = dict(
            event_id=eid, company_id="co1", actor_id="actor", kind=kind,
            source=BusinessSource(kind.lower(), source or ("biz-" + eid)),
            warehouse_id="wh1", item_id="sku1", unit="kg",
            base_units_per_unit=1000, quantity_base=qty)
        payload.update(fields)
        return StockEvent(**payload)

    def put(self, event):
        authority = StockAuthority(
            "co1", frozenset({"actor"}), frozenset({"wh1", "wh2"}),
            frozenset({"sku1"}),
            frozenset({(event.source.kind, event.source.source_id)}),
            project_ids=frozenset({"p"}), work_scopes=frozenset({
                ("p", "job1", "CC-0001"),
            }))
        self.stock = append_stock_event(self.stock, event, authority,
                                        expected_revision=self.stock.revision)
        return event

    def scopes(self):
        return VerifiedScopes(
            party_ids=frozenset({"vendor1"}),
            project_ids=frozenset({"p"}),
            task_scopes=frozenset({("p", "task1")}),
            independent_source_scopes=frozenset({
                (e.event.project_id, e.event.source.source_id)
                for e in self.stock.events}),
        )

    def context(self, *, date="2026-06-01", period="P", mode="COGS",
                actor="actor", stock_rev=None, journal_rev=None):
        return VerifiedGLPosting(
            "co1", actor, period, date, "2026-10-22",
            stock_rev or self.stock.revision, journal_rev or self.journal.revision,
            mode)

    def settlement(self, event, amount, mode="GRNI", *,
                   invoice_id=None, party_id=None):
        return VerifiedReceiptSettlement(
            "co1", event.event_id, event.source.source_id, mode, amount,
            invoice_id if invoice_id is not None else
            (event.source.source_id if mode == "AP" else ""),
            party_id if party_id is not None else
            ("vendor1" if mode == "AP" else ""))

    def run_bridge(self, event, *, settlement=None, context=None, scopes=None,
                   chart=None, accounts=None, stock=None, journal=None, policy=None,
                   save=True):
        result = apply_inventory_gl(
            stock if stock is not None else self.stock,
            journal if journal is not None else self.journal,
            event.event_id,
            chart=chart if chart is not None else self.chart,
            scopes=scopes if scopes is not None else self.scopes(),
            accounts=accounts if accounts is not None else self.map,
            context=context if context is not None else self.context(),
            money_policy=policy if policy is not None else self.policy,
            settlement=settlement,
        )
        if save:
            self.journal = result.journal
        return result

    def test_receipt_grni_balanced_and_rial_only(self):
        event = self.put(self.movement("RECEIPT", "r1", 3, cost_rial=10))
        result = self.run_bridge(event, settlement=self.settlement(event, 10))
        self.assertEqual(result.status, "POSTED")
        self.assertEqual(result.amount_rial, 10)
        self.assertEqual(len(result.journal.events), 1)
        lines = result.journal.events[0].lines
        self.assertEqual([(l.reference.account_code, l.debit_rial, l.credit_rial)
                          for l in lines],
                         [("100101", 10, 0), ("200101", 0, 10)])
        self.assertEqual(replay_journal(result.journal).posted_count, 1)
        self.assertEqual(result.journal.currency, "RIAL")

    def test_ap_invoice_requires_verified_party_and_one_source(self):
        receipt = self.put(self.movement("RECEIPT", "ap1", 6,
                                         source="invoice-1", cost_rial=77))
        result = self.run_bridge(receipt, settlement=self.settlement(
            receipt, 77, "AP"))
        self.assertEqual(result.receipt_invoice_id, "invoice-1")
        invoice_line = result.journal.events[-1].lines[1]
        self.assertEqual(invoice_line.reference.account_code, "200102")
        self.assertEqual(invoice_line.reference.party_id, "vendor1")
        self.assertEqual(invoice_line.reference.detail_code, "FD-000001")
        self.assertEqual(invoice_line.credit_rial, 77)

    def test_ap_wrong_invoice_identity_and_amount_denied(self):
        receipt = self.put(self.movement("RECEIPT", "r1", 3, cost_rial=10))
        with self.assertRaises(InventoryBridgeError):
            self.run_bridge(receipt, settlement=self.settlement(
                receipt, 10, "AP", invoice_id="different"))
        with self.assertRaises(InventoryBridgeError):
            self.run_bridge(receipt, settlement=self.settlement(receipt, 11))
        with self.assertRaises(InventoryBridgeError):
            self.run_bridge(receipt, settlement=self.settlement(
                receipt, 10, "AP", party_id="foreign"))
        self.assertEqual(self.journal.events, ())

    def test_costless_intake_never_posts_ap_or_inventory(self):
        receipt = self.put(self.movement("RECEIPT", "r1", 7, cost_rial=None))
        noop = self.run_bridge(receipt)
        self.assertEqual(noop.status, "NO_GL")
        self.assertEqual(noop.journal.events, ())
        self.assertEqual(noop.amount_rial, 0)
        with self.assertRaises(InventoryBridgeError):
            self.run_bridge(receipt, settlement=self.settlement(
                receipt, 99, "AP"))
        self.assertEqual(self.journal.events, ())

    def test_price_after_staging_books_exact_asset_to_grni(self):
        receipt = self.put(self.movement("RECEIPT", "r1", 5))
        self.assertEqual(self.run_bridge(receipt).status, "NO_GL")
        price = self.put(self.movement("PRICE", "price1", 5, cost_rial=123,
                                       related_event_id="r1"))
        posted = self.run_bridge(price, settlement=self.settlement(price, 123))
        self.assertEqual(posted.amount_rial, 123)
        self.assertEqual(posted.journal.events[0].lines[1].reference.account_code,
                         "200101")
        self.assertEqual(replay_journal(self.journal).posted_count, 1)

    def test_fifo_issue_expense_exact_remainder(self):
        receipt = self.put(self.movement("RECEIPT", "r1", 3, cost_rial=10))
        self.run_bridge(receipt, settlement=self.settlement(receipt, 10))
        issue1 = self.put(self.movement("ISSUE", "i1", 1))
        posted1 = self.run_bridge(issue1)
        self.assertEqual(posted1.amount_rial, 3)
        self.assertEqual(posted1.journal.events[-1].lines[0].reference.account_code,
                         "500101")
        issue2 = self.put(self.movement("ISSUE", "i2", 2))
        self.assertEqual(self.run_bridge(issue2).amount_rial, 7)
        self.assertEqual(replay_journal(self.journal).posted_count, 3)

    def test_wip_requires_project_job_and_bound_cost_center(self):
        receipt = self.put(self.movement("RECEIPT", "r1", 3, cost_rial=30,
                                         project_id="p",
                                         job_id="job1", cost_center_id="CC-0001"))
        self.run_bridge(receipt, settlement=self.settlement(receipt, 30))
        issue = self.put(self.movement("ISSUE", "i1", 1, project_id="p",
                                       job_id="job1", cost_center_id="CC-0001"))
        with self.assertRaises(InventoryBridgeError):
            self.run_bridge(issue)
        result = self.run_bridge(issue, context=self.context(mode="WIP"))
        self.assertEqual(result.journal.events[-1].lines[0].reference.account_code,
                         "100102")
        ref = result.journal.events[-1].lines[0].reference
        self.assertEqual((ref.project_id, ref.job_id, ref.cost_center_code, ref.task_id),
                         ("p", "job1", "CC-0001", "task1"))

    def test_wip_without_job_fails(self):
        receipt = self.put(self.movement("RECEIPT", "r", 2, cost_rial=20))
        self.run_bridge(receipt, settlement=self.settlement(receipt, 20))
        issue = self.put(self.movement("ISSUE", "issue", 1))
        with self.assertRaises(InventoryBridgeError):
            self.run_bridge(issue, context=self.context(mode="WIP"))

    def test_interwarehouse_transfer_is_not_an_ap_or_gl_post(self):
        receipt = self.put(self.movement("RECEIPT", "r", 3, cost_rial=30))
        self.run_bridge(receipt, settlement=self.settlement(receipt, 30))
        transfer = self.put(self.movement(
            "TRANSFER", "x", 2, destination_warehouse_id="wh2"))
        prior = self.journal
        result = self.run_bridge(transfer)
        self.assertEqual(result.status, "NO_GL")
        self.assertIs(result.journal, prior)
        self.assertEqual(len(result.journal.events), 1)
        with self.assertRaises(InventoryBridgeError):
            self.run_bridge(transfer, settlement=self.settlement(transfer, 10, "AP"))

    def test_transfer_still_needs_host_verified_source(self):
        receipt = self.put(self.movement("RECEIPT", "r", 3, cost_rial=30))
        self.run_bridge(receipt, settlement=self.settlement(receipt, 30))
        transfer = self.put(self.movement(
            "TRANSFER", "x", 2, destination_warehouse_id="wh2"))
        with self.assertRaises(InventoryBridgeError):
            self.run_bridge(transfer, scopes=replace(
                self.scopes(), independent_source_scopes=frozenset()))

    def test_nonposting_source_with_preexisting_financial_journal_denied(self):
        receipt = self.put(self.movement("RECEIPT", "r", 3))
        alien = post_journal(
            self.journal, company_id="co1", fiscal_period_id="P",
            event_id="legacy-alien", actor_id="actor",
            posting_date="2026-06-01",
            source=JournalSource("independent", receipt.source.source_id),
            lines=(JournalLine(PostingReference("co1", "100101"), debit_rial=8),
                   JournalLine(PostingReference("co1", "200101"), credit_rial=8)),
            chart=self.chart, scopes=self.scopes(), money_policy=self.policy,
            expected_revision=self.journal.revision, today="2026-10-22",
        )
        with self.assertRaises(InventoryBridgeConflict):
            self.run_bridge(receipt, journal=alien)

    def test_return_reverses_original_v2_journal_exactly_with_reference(self):
        receipt = self.put(self.movement("RECEIPT", "r", 5, cost_rial=25))
        self.run_bridge(receipt, settlement=self.settlement(receipt, 25))
        issue = self.put(self.movement("ISSUE", "i", 2))
        first = self.run_bridge(issue)
        returned = self.put(self.movement("RETURN", "ret", 2, related_event_id="i",
                                          reason="Goods came back"))
        result = self.run_bridge(returned, context=self.context(date="2026-06-02"))
        self.assertEqual(result.status, "REVERSED")
        self.assertEqual(result.amount_rial, 10)
        self.assertEqual(result.journal.events[-1].reversal_of, first.journal_event_id)
        original = first.journal.events[-1]
        reversed_lines = result.journal.events[-1].lines
        self.assertEqual([(l.debit_rial, l.credit_rial) for l in reversed_lines],
                         [(l.credit_rial, l.debit_rial) for l in original.lines])
        replay_journal(self.journal)

    def test_reversal_of_payables_preserves_original_party_details(self):
        receipt = self.put(self.movement(
            "RECEIPT", "r", 5, source="invoice-5", cost_rial=50))
        booked = self.run_bridge(receipt, settlement=self.settlement(
            receipt, 50, "AP"))
        reversal = self.put(self.movement(
            "REVERSAL", "rv", 5, related_event_id="r",
            reason="Supplier document voided"))
        result = self.run_bridge(reversal, context=self.context(date="2026-06-02"))
        self.assertEqual(result.status, "REVERSED")
        self.assertEqual(result.journal.events[-1].reversal_of, booked.journal_event_id)
        self.assertEqual(result.journal.events[-1].lines[1].reference.party_id, "vendor1")
        self.assertEqual(result.journal.events[-1].lines[1].debit_rial, 50)

    def test_historical_reversal_can_use_original_frozen_chart_evidence(self):
        receipt = self.put(self.movement(
            "RECEIPT", "r", 3, cost_rial=30))
        self.run_bridge(receipt, settlement=self.settlement(receipt, 30))
        reversal = self.put(self.movement(
            "REVERSAL", "rvr", 3, related_event_id="r",
            reason="Voided purchase"))
        result = self.run_bridge(reversal, context=self.context(date="2026-06-02"),
                                 chart=fixture_chart(freeze_inventory=True))
        self.assertEqual(result.status, "REVERSED")
        self.assertEqual(result.journal.events[-1].reversal_of,
                         result.journal.events[0].event_id)

    def test_exact_reversal_retry_and_changed_date_conflict(self):
        receipt = self.put(self.movement("RECEIPT", "r", 2, cost_rial=20))
        self.run_bridge(receipt, settlement=self.settlement(receipt, 20))
        reversal = self.put(self.movement(
            "REVERSAL", "rv", 2, related_event_id="r", reason="Correction"))
        context = self.context(date="2026-06-02")
        first = self.run_bridge(reversal, context=context)
        again = self.run_bridge(reversal, context=self.context(date="2026-06-02"))
        self.assertEqual(again.status, "IDEMPOTENT")
        self.assertIs(again.journal, first.journal)
        with self.assertRaises(InventoryBridgeConflict):
            self.run_bridge(reversal, context=self.context(date="2026-06-03"))

    def test_return_source_reuse_under_different_gl_id_is_conflict(self):
        receipt = self.put(self.movement("RECEIPT", "r", 4, cost_rial=40))
        self.run_bridge(receipt, settlement=self.settlement(receipt, 40))
        issue = self.put(self.movement("ISSUE", "i", 2))
        self.run_bridge(issue)
        ret = self.put(self.movement(
            "RETURN", "ret", 2, related_event_id="i", reason="Customer return"))
        alien = post_journal(
            self.journal, company_id="co1", fiscal_period_id="P",
            event_id="other-financial-event", actor_id="actor",
            posting_date="2026-06-01",
            source=JournalSource("independent", ret.source.source_id),
            lines=(JournalLine(PostingReference("co1", "100101"), debit_rial=1),
                   JournalLine(PostingReference("co1", "200101"), credit_rial=1)),
            chart=self.chart, scopes=self.scopes(), money_policy=self.policy,
            expected_revision=self.journal.revision, today="2026-10-22",
        )
        with self.assertRaises(InventoryBridgeConflict):
            self.run_bridge(ret, journal=alien,
                            context=self.context(date="2026-06-02",
                                                 journal_rev=alien.revision))
        self.assertEqual(len(alien.events), 3)

    def test_missing_original_journal_refuses_orphan_return(self):
        receipt = self.put(self.movement("RECEIPT", "r", 5, cost_rial=50))
        self.run_bridge(receipt, settlement=self.settlement(receipt, 50))
        issue = self.put(self.movement("ISSUE", "i", 1))
        returned = self.put(self.movement("RETURN", "ret", 1, related_event_id="i",
                                          reason="Returned"))
        with self.assertRaises(InventoryBridgeError):
            self.run_bridge(returned)
        self.assertEqual(len(self.journal.events), 1)

    def test_exact_retry_is_idempotent_without_second_post(self):
        receipt = self.put(self.movement("RECEIPT", "r", 3, cost_rial=10))
        context = self.context()
        proof = self.settlement(receipt, 10)
        first = self.run_bridge(receipt, settlement=proof, context=context)
        second = self.run_bridge(receipt, settlement=proof)
        self.assertEqual(second.status, "IDEMPOTENT")
        self.assertIs(second.journal, first.journal)
        self.assertEqual(len(self.journal.events), 1)
        with self.assertRaises(InventoryBridgeConflict):
            self.run_bridge(receipt, settlement=proof, context=context)

    def test_duplicate_business_source_in_v2_under_different_event_id_refused(self):
        receipt = self.put(self.movement("RECEIPT", "r", 3, cost_rial=10))
        source = JournalSource("independent", receipt.source.source_id)
        alien = post_journal(
            self.journal, company_id="co1", fiscal_period_id="P",
            event_id="alien-v2-event", actor_id="actor",
            posting_date="2026-06-01", source=source,
            lines=(
                JournalLine(PostingReference("co1", "100101"), debit_rial=1),
                JournalLine(PostingReference("co1", "200101"), credit_rial=1)),
            chart=self.chart, scopes=self.scopes(), money_policy=self.policy,
            expected_revision=self.journal.revision, today="2026-10-22")
        with self.assertRaises(InventoryBridgeConflict):
            self.run_bridge(receipt, settlement=self.settlement(receipt, 10),
                            journal=alien)
        self.assertEqual(len(alien.events), 1)

    def test_cross_company_and_forged_actor_denied(self):
        receipt = self.put(self.movement("RECEIPT", "r", 3, cost_rial=10))
        settlement = self.settlement(receipt, 10)
        with self.assertRaises(InventoryBridgeError):
            self.run_bridge(receipt, settlement=settlement,
                            context=replace(self.context(), company_id="foreign"))
        with self.assertRaises(InventoryBridgeError):
            self.run_bridge(receipt, settlement=settlement,
                            context=self.context(actor="intruder"))
        with self.assertRaises(InventoryBridgeError):
            self.run_bridge(receipt, settlement=settlement,
                            policy=CompanyMoneyPolicy("foreign"))
        with self.assertRaises(InventoryBridgeError):
            self.run_bridge(receipt, settlement=settlement,
                            accounts=VerifiedInventoryAccounts(
                                replace(self.base, company_id="foreign"), "200102", "100102"))
        self.assertEqual(self.journal.events, ())

    def test_project_and_source_proof_must_match(self):
        receipt = self.put(self.movement(
            "RECEIPT", "r", 3, cost_rial=12, project_id="p"))
        with self.assertRaises(InventoryBridgeError):
            self.run_bridge(receipt, settlement=self.settlement(receipt, 12),
                            scopes=VerifiedScopes(independent_source_scopes=frozenset({
                                ("", receipt.source.source_id)})))
        with self.assertRaises(InventoryBridgeError):
            self.run_bridge(receipt, settlement=self.settlement(receipt, 12),
                            scopes=replace(self.scopes(),
                                           independent_source_scopes=frozenset()))
        self.assertEqual(self.journal.events, ())

    def test_bad_mapping_frozen_account_and_chart_wrong_kind_refused(self):
        receipt = self.put(self.movement("RECEIPT", "r", 3, cost_rial=12))
        with self.assertRaises(InventoryBridgeError):
            self.run_bridge(receipt, settlement=self.settlement(receipt, 12),
                            chart=fixture_chart(freeze_inventory=True))
        with self.assertRaises(InventoryBridgeError):
            self.run_bridge(receipt, settlement=self.settlement(receipt, 12),
                            accounts=VerifiedInventoryAccounts(
                                replace(self.base, receipt_clearing="100102"),
                                "200102", "100103"))

    def test_closed_period_and_stale_revisions_fail_closed(self):
        receipt = self.put(self.movement("RECEIPT", "r", 3, cost_rial=12))
        with self.assertRaises(InventoryBridgeConflict):
            self.run_bridge(receipt, settlement=self.settlement(receipt, 12),
                            context=self.context(stock_rev="0" * 64))
        with self.assertRaises(InventoryBridgeConflict):
            self.run_bridge(receipt, settlement=self.settlement(receipt, 12),
                            context=self.context(journal_rev="0" * 64))
        self.journal = close_fiscal_period(
            self.journal, company_id="co1", fiscal_period_id="P",
            event_id="closed", actor_id="actor", closing_date="2027-01-01",
            expected_revision=self.journal.revision, today="2027-01-01")
        with self.assertRaises(InventoryBridgeError):
            self.run_bridge(receipt, settlement=self.settlement(receipt, 12))

    def test_adjustment_rejected_without_explicit_journal_policy(self):
        receipt = self.put(self.movement("RECEIPT", "r", 3, cost_rial=12))
        count = self.put(self.movement(
            "ADJUSTMENT", "count", 1, expected_quantity_base=3,
            counted_quantity_base=2, reason="Verified shelf count"))
        with self.assertRaises(InventoryBridgeError):
            self.run_bridge(count)
        self.assertEqual(self.journal.events, ())

    def test_reversal_cannot_change_original_financial_amount(self):
        receipt = self.put(self.movement("RECEIPT", "r", 5, cost_rial=25))
        self.run_bridge(receipt, settlement=self.settlement(receipt, 25))
        issue = self.put(self.movement("ISSUE", "i", 2))
        # Inject a separately valid but unrelated amount under canonical source ID
        wrong_journal = post_journal(
            self.journal, company_id="co1", fiscal_period_id="P",
            event_id=_journal_id("co1", issue.source.source_id), actor_id="actor",
            posting_date="2026-06-01", source=JournalSource(
                "independent", issue.source.source_id),
            lines=(
                JournalLine(PostingReference("co1", "500101"), debit_rial=9),
                JournalLine(PostingReference("co1", "100101"), credit_rial=9)),
            chart=self.chart, scopes=self.scopes(), money_policy=self.policy,
            expected_revision=self.journal.revision, today="2026-10-22")
        returned = self.put(self.movement(
            "RETURN", "returned", 2, related_event_id="i", reason="Return"))
        with self.assertRaises(InventoryBridgeError):
            self.run_bridge(returned, journal=wrong_journal)


if __name__ == "__main__":
    unittest.main()
