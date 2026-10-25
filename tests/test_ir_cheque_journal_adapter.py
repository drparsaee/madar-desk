"""Synthetic adversarial bridge tests; no APPDATA, database or host IO."""
from dataclasses import replace, FrozenInstanceError
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ir_chart_model import ChartAccount, ChartSnapshot, PostingReference
from ir_journal_v2 import (
    FiscalPeriod, JournalLine, JournalSource, PostedJournal, VerifiedScopes,
    new_journal_state, post_journal, replay_journal, reverse_journal,
    close_fiscal_period,
)
from ir_treasury_cheques import (
    ChequeBusinessSource, ChequeCommand, ChequeInstrument, ChequePeriod,
    VerifiedChequeRefs, new_cheque_state, append_cheque_event,
)
from ir_cheque_journal_adapter import (
    ChequeGLAccounts, ChequeGLError, ChequeGLConflict, VerifiedChequeGLContext,
    cheque_journal_source_id, propose_cheque_journal, post_cheque_journal,
)
from money_policy import CompanyMoneyPolicy, MAX_RIAL

TODAY = "2026-11-15"
CORRECT_DATES = {
    "1405-03-01": "2026-05-22",
    "1405-04-01": "2026-06-22",
    "1405-06-03": "2026-08-25",
    "1405-06-04": "2026-08-26",
    "1405-06-05": "2026-08-27",
    "1405-07-05": "2026-09-27",
    "1405-07-10": "2026-10-02",
}

def chart(company="co-A"):
    accts = [
        ChartAccount(company, "10", "KOL", None, "Assets", "asset"),
        ChartAccount(company, "1001", "MOEIN", "10", "Cheques and cash", "asset"),
        *[ChartAccount(company, f"1001{i:02}", "TAFSILI", "1001",
                       f"Asset {i}", "asset", accountable=True)
          for i in range(1, 7)],
        ChartAccount(company, "20", "KOL", None, "Liabilities", "liability"),
        ChartAccount(company, "2001", "MOEIN", "20", "Payables", "liability"),
        *[ChartAccount(company, f"2001{i:02}", "TAFSILI", "2001",
                       f"Liability {i}", "liability", accountable=True)
          for i in range(1, 3)],
    ]
    return ChartSnapshot(company_id=company, accounts=tuple(accts))


def mapping(company="co-A", cheque_id="check-1", party="customer-A",
            bank="bank-A", account="own-A", supplier="supplier-A"):
    def ref(code, person=""):
        return PostingReference(company, code, party_id=person)
    return ChequeGLAccounts(
        company, cheque_id, party, bank, account,
        in_hand=ref("100101"), transferred=ref("100102"),
        deposited=ref("100103"), bank=ref("100104"),
        ar=ref("100105", party), ap=ref("200101", party),
        returned=ref("100106"), payable=ref("200102"),
        supplier_party_id=supplier,
    )


def cheque_state(company="co-A"):
    return new_cheque_state(company, (
        ChequePeriod(company, "FY1", "1405-01-01", "1405-06-31"),
        ChequePeriod(company, "FY2", "1405-07-01", "1405-12-29"),
    ))


def journal_state(company="co-A"):
    return new_journal_state(company, (
        FiscalPeriod(company, "FY1", "2026-03-21", "2026-09-22"),
        FiscalPeriod(company, "FY2", "2026-09-23", "2027-03-20"),
    ))


def cheque_scope(company="co-A"):
    return VerifiedChequeRefs(
        company,
        frozenset({"customer-A", "supplier-A", "customer-B"}),
        frozenset({"bank-A", "bank-B"}),
        frozenset({("bank-A", "own-A"), ("bank-B", "own-B")}),
        supplier_party_ids=frozenset({"supplier-A"}),
    )


def scope_for(state, company=None, *, drop_source=""):
    company = company or state.company_id
    sources = frozenset({
        ("", cheque_journal_source_id(company, event.command.cheque_id,
                                       event.command.event_id))
        for event in state.events
        if event.command.event_id != drop_source
    })
    return VerifiedScopes(
        party_ids=frozenset({"customer-A", "supplier-A", "customer-B"}),
        independent_source_scopes=sources,
    )


def register(direction="RECEIVABLE", *, company="co-A",
             amount=101, cheque_id="check-1"):
    old = cheque_state(company)
    payable = direction == "PAYABLE"
    cmd = ChequeCommand(
        "event-1", company, "FY1", "actor-A", "1405-03-01", cheque_id,
        "ISSUE" if payable else "RECEIVE",
        ChequeBusinessSource("purchase" if payable else "invoice", "source-1"),
        instrument=ChequeInstrument(
            company, cheque_id, "instrument-1", direction, amount,
            "bank-A" if payable else "bank-B",
            "own-A" if payable else "external-A",
            "supplier-A" if payable else "customer-A", "1405-06-01",
        ),
    )
    return append_cheque_event(old, cmd, scopes=cheque_scope(company),
                               expected_revision=old.revision, today="1405-11-01")


def advance(old, action, *, event="event-2", day="1405-06-03",
            cheque_id="check-1", bank="", account="", supplier="",
            target="", reason=""):
    period = "FY1" if day < "1405-07-01" else "FY2"
    cmd = ChequeCommand(
        event, old.company_id, period, "actor-A", day, cheque_id, action,
        ChequeBusinessSource("bank", event),
        bank_id=bank, bank_account_id=account, supplier_party_id=supplier,
        reverses_event_id=target, reason=reason,
    )
    return append_cheque_event(
        old, cmd, scopes=cheque_scope(old.company_id),
        expected_revision=old.revision, today="1405-11-01")


def context(state, event, *, calendar_date=None, accrued=True,
            transfer_policy="UNSPECIFIED"):
    cmd = next(x.command for x in state.events if x.command.event_id == event)
    return VerifiedChequeGLContext(
        state.company_id, cmd.cheque_id, event, cmd.event_date,
        calendar_date or CORRECT_DATES[cmd.event_date],
        cmd.fiscal_period_id, cmd.actor_id, accrued, transfer_policy)


def proposal(chq, jrn, event, *, mappings=None, accounts=None,
             verified=None, ctx=None, money=None):
    return propose_cheque_journal(
        chq, jrn, cheque_event_id=event,
        mapping=mappings or mapping(
            chq.company_id, party="supplier-A" if
            chq.events[0].command.instrument.direction == "PAYABLE"
            else "customer-A"),
        chart=accounts or chart(chq.company_id),
        scopes=verified or scope_for(chq),
        money_policy=money or CompanyMoneyPolicy(chq.company_id),
        context=ctx or context(chq, event), today=TODAY,
    )


def post(chq, old, event, *, mappings=None, accounts=None,
         verified=None, ctx=None, money=None):
    mapping_arg = mappings or mapping(
        chq.company_id, party="supplier-A" if
        chq.events[0].command.instrument.direction == "PAYABLE"
        else "customer-A")
    chart_arg = accounts or chart(chq.company_id)
    scope_arg = verified or scope_for(chq)
    policy_arg = money or CompanyMoneyPolicy(chq.company_id)
    context_arg = ctx or context(chq, event)
    proposed = proposal(
        chq, old, event, mappings=mapping_arg, accounts=chart_arg,
        verified=scope_arg, ctx=context_arg, money=policy_arg)
    if proposed is None:
        return old, None
    saved = post_cheque_journal(
        chq, old, proposal=proposed, mapping=mapping_arg,
        chart=chart_arg, scopes=scope_arg, money_policy=policy_arg,
        context=context_arg, today=TODAY,
        expected_journal_revision=old.revision,
    )
    return saved, proposed


class ChequeJournalBridgeTests(unittest.TestCase):
    def reject(self, cb, error=(ChequeGLError, ValueError)):
        with self.assertRaises(error):
            cb()

    def test_receipt_balanced_exact_one_rial_and_source_id(self):
        chq = register(amount=1)
        jrn, p = post(chq, journal_state(), "event-1")
        self.assertEqual(p.amount_rial, 1)
        self.assertEqual(p.cash_effect, "NONE")
        self.assertEqual([(v.reference.account_code, v.debit_rial, v.credit_rial)
                          for v in p.lines], [
                              ("100101", 1, 0), ("100105", 0, 1)])
        self.assertEqual(p.source.kind, "independent")
        self.assertEqual(p.source.source_id, cheque_journal_source_id(
            "co-A", "check-1", "event-1"))
        self.assertEqual(p.event_id, jrn.events[0].event_id)
        self.assertEqual(replay_journal(jrn).posted_count, 1)

    def test_payable_issue_ap_debit_cheques_payable_credit(self):
        chq = register("PAYABLE")
        jrn, p = post(chq, journal_state(), "event-1")
        self.assertEqual([x.reference.account_code for x in p.lines],
                         ["200101", "200102"])
        self.assertEqual(p.lines[0].debit_rial, 101)
        self.assertEqual(p.lines[1].credit_rial, 101)
        self.assertEqual(p.cash_effect, "NONE")
        self.assertEqual(len(jrn.events), 1)

    def test_receivable_deposit_does_not_debit_bank_only_clear_does(self):
        chq = register()
        jrn, p1 = post(chq, journal_state(), "event-1")
        chq = advance(chq, "DEPOSIT", bank="bank-A", account="own-A")
        jrn, p2 = post(chq, jrn, "event-2")
        self.assertEqual([line.reference.account_code for line in p2.lines],
                         ["100103", "100101"])
        self.assertNotIn("100104", [x.reference.account_code for x in p1.lines + p2.lines])
        self.assertEqual(p2.cash_effect, "NONE")
        chq = advance(chq, "CLEAR", event="event-3", day="1405-07-05")
        jrn, p3 = post(chq, jrn, "event-3")
        self.assertEqual([x.reference.account_code for x in p3.lines],
                         ["100104", "100103"])
        self.assertEqual(p3.cash_effect, "DEBIT_BANK")
        self.assertEqual(sum(line.debit_rial for event in jrn.events
                             if type(event) is PostedJournal for line in event.lines
                             if line.reference.account_code == "100104"), 101)

    def test_payable_presentation_memo_and_clearing_cash_credit(self):
        chq = register("PAYABLE")
        jrn, _ = post(chq, journal_state(), "event-1")
        chq = advance(chq, "PRESENT")
        unchanged, empty = post(chq, jrn, "event-2")
        self.assertIs(unchanged, jrn)
        self.assertIsNone(empty)
        chq = advance(chq, "CLEAR", event="event-3", day="1405-07-05")
        jrn, p = post(chq, jrn, "event-3")
        self.assertEqual([x.reference.account_code for x in p.lines],
                         ["200102", "100104"])
        self.assertEqual(p.cash_effect, "CREDIT_BANK")
        self.assertEqual(len(jrn.events), 2)

    def test_receivable_bounce_redeposit_and_clearing_balances(self):
        chq = register()
        jrn, _ = post(chq, journal_state(), "event-1")
        chq = advance(chq, "DEPOSIT", bank="bank-A", account="own-A")
        jrn, _ = post(chq, jrn, "event-2")
        chq = advance(chq, "BOUNCE", event="event-3",
                      day="1405-06-04", reason="Unpaid")
        jrn, bounced = post(chq, jrn, "event-3")
        self.assertEqual([x.reference.account_code for x in bounced.lines],
                         ["100106", "100103"])
        chq = advance(chq, "REDEPOSIT", event="event-4",
                      day="1405-06-05", bank="bank-A", account="own-A")
        jrn, again = post(chq, jrn, "event-4")
        self.assertEqual([x.reference.account_code for x in again.lines],
                         ["100103", "100106"])
        chq = advance(chq, "CLEAR", event="event-5", day="1405-07-05")
        jrn, cleared = post(chq, jrn, "event-5")
        self.assertEqual(cleared.cash_effect, "DEBIT_BANK")
        self.assertEqual(replay_journal(jrn).posted_count, 5)
        self.assertEqual(sum(e.cash_effect != "NONE" for e in
                             (bounced, again, cleared)), 1)

    def test_payable_bounce_and_represent_no_gl_posting(self):
        chq = register("PAYABLE")
        jrn, _ = post(chq, journal_state(), "event-1")
        chq = advance(chq, "PRESENT")
        self.assertIsNone(proposal(chq, jrn, "event-2"))
        chq = advance(chq, "BOUNCE", event="event-3",
                      day="1405-06-04", reason="Unpaid")
        self.assertIsNone(proposal(chq, jrn, "event-3"))
        chq = advance(chq, "REPRESENT", event="event-4", day="1405-06-05")
        self.assertIsNone(proposal(chq, jrn, "event-4"))
        self.assertEqual(len(jrn.events), 1)

    def test_return_of_received_cheque_reinstates_ar(self):
        chq = register()
        jrn, _ = post(chq, journal_state(), "event-1")
        chq = advance(chq, "RETURN", day="1405-04-01",
                      reason="Returned to payer")
        jrn, p = post(chq, jrn, "event-2")
        self.assertEqual([l.reference.account_code for l in p.lines],
                         ["100105", "100101"])

    def test_return_of_bounced_receivable_reinstates_ar(self):
        chq = register()
        jrn, _ = post(chq, journal_state(), "event-1")
        chq = advance(chq, "DEPOSIT", bank="bank-A", account="own-A")
        jrn, _ = post(chq, jrn, "event-2")
        chq = advance(chq, "BOUNCE", event="event-3",
                      day="1405-06-04", reason="Unpaid")
        jrn, _ = post(chq, jrn, "event-3")
        chq = advance(chq, "RETURN", event="event-4",
                      day="1405-06-05", reason="Return to customer")
        jrn, p = post(chq, jrn, "event-4")
        self.assertEqual([l.reference.account_code for l in p.lines],
                         ["100105", "100106"])

    def test_payable_cancel_reinstates_ap_instead_of_crediting_cash(self):
        chq = register("PAYABLE")
        jrn, _ = post(chq, journal_state(), "event-1")
        chq = advance(chq, "CANCEL", day="1405-04-01",
                      reason="Recovered voided paper")
        jrn, p = post(chq, jrn, "event-2")
        self.assertEqual([l.reference.account_code for l in p.lines],
                         ["200102", "200101"])
        self.assertEqual(p.cash_effect, "NONE")

    def test_payable_return_after_bounce_reinstates_ap(self):
        chq = register("PAYABLE")
        jrn, _ = post(chq, journal_state(), "event-1")
        chq = advance(chq, "PRESENT")
        chq = advance(chq, "BOUNCE", event="event-3",
                      day="1405-06-04", reason="Unpaid")
        chq = advance(chq, "RETURN", event="event-4",
                      day="1405-06-05", reason="Recovered original")
        jrn, p = post(chq, jrn, "event-4")
        self.assertEqual([l.reference.account_code for l in p.lines],
                         ["200102", "200101"])

    def test_endorse_requires_explicit_pending_policy_and_supplier(self):
        chq = register()
        jrn, _ = post(chq, journal_state(), "event-1")
        chq = advance(chq, "ENDORSE", day="1405-04-01", supplier="supplier-A")
        self.reject(lambda: proposal(chq, jrn, "event-2"))
        ctx = context(chq, "event-2", transfer_policy="PENDING_TRANSFER_ONLY")
        jrn, p = post(chq, jrn, "event-2", ctx=ctx)
        self.assertEqual([l.reference.account_code for l in p.lines],
                         ["100102", "100101"])
        self.assertEqual(p.cash_effect, "NONE")
        bad_map = replace(mapping(), supplier_party_id="customer-A")
        self.reject(lambda: proposal(chq, jrn, "event-2",
                                     mappings=bad_map, ctx=ctx))

    def test_endorsed_return_ambiguous_fails_closed(self):
        chq = register()
        jrn, _ = post(chq, journal_state(), "event-1")
        chq = advance(chq, "ENDORSE", day="1405-04-01", supplier="supplier-A")
        ctx = context(chq, "event-2", transfer_policy="PENDING_TRANSFER_ONLY")
        jrn, _ = post(chq, jrn, "event-2", ctx=ctx)
        chq = advance(chq, "RETURN", event="event-3",
                      day="1405-06-03", reason="Unclear holder legal status")
        self.reject(lambda: proposal(chq, jrn, "event-3"))

    def test_reverse_deposit_restores_hand_without_bank_cash(self):
        chq = register()
        jrn, _ = post(chq, journal_state(), "event-1")
        chq = advance(chq, "DEPOSIT", bank="bank-A", account="own-A")
        jrn, _ = post(chq, jrn, "event-2")
        chq = advance(chq, "REVERSE", event="event-3", day="1405-06-04",
                      target="event-2", reason="Verified bank cancellation")
        jrn, p = post(chq, jrn, "event-3")
        self.assertEqual([l.reference.account_code for l in p.lines],
                         ["100101", "100103"])
        self.assertEqual(p.cash_effect, "NONE")

    def test_reverse_bounce_reverses_prior_gl_stage(self):
        chq = register()
        jrn, _ = post(chq, journal_state(), "event-1")
        chq = advance(chq, "DEPOSIT", bank="bank-A", account="own-A")
        jrn, _ = post(chq, jrn, "event-2")
        chq = advance(chq, "BOUNCE", event="event-3",
                      day="1405-06-04", reason="Unpaid")
        jrn, _ = post(chq, jrn, "event-3")
        chq = advance(chq, "REVERSE", event="event-4",
                      day="1405-06-05", target="event-3",
                      reason="Bank changed status")
        jrn, p = post(chq, jrn, "event-4")
        self.assertEqual([l.reference.account_code for l in p.lines],
                         ["100103", "100106"])

    def test_missing_prior_accounting_stage_rejected(self):
        chq = advance(register(), "DEPOSIT", bank="bank-A", account="own-A")
        self.reject(lambda: proposal(chq, journal_state(), "event-2"),
                    ChequeGLConflict)

    def test_journal_reversal_of_required_earlier_stage_fails_closed(self):
        chq = register()
        jrn, posted = post(chq, journal_state(), "event-1")
        undone = reverse_journal(
            jrn, company_id="co-A", original_event_id=posted.event_id,
            event_id="reversal-ledger-1", actor_id="actor-A",
            fiscal_period_id="FY1", posting_date="2026-05-23",
            reason="Bank document disputed",
            expected_revision=jrn.revision, today=TODAY,
        )
        chq = advance(chq, "DEPOSIT", bank="bank-A", account="own-A")
        self.reject(lambda: proposal(chq, undone, "event-2"), ChequeGLConflict)

    def test_cannot_post_later_stage_before_prior_journal_date(self):
        chq = register()
        jrn, _ = post(chq, journal_state(), "event-1")
        chq = advance(chq, "DEPOSIT", bank="bank-A", account="own-A")
        forged_pair = replace(context(chq, "event-2"),
                              gregorian_posting_date="2026-05-21")
        self.reject(lambda: proposal(chq, jrn, "event-2", ctx=forged_pair),
                    ChequeGLConflict)

    def test_memo_with_spurious_journal_occupancy_rejected(self):
        chq = advance(register("PAYABLE"), "PRESENT")
        jrn, _ = post(chq, journal_state(), "event-1")
        source = JournalSource("independent", cheque_journal_source_id(
            "co-A", "check-1", "event-2"))
        s = scope_for(chq)
        forged = post_journal(
            jrn, company_id="co-A", fiscal_period_id="FY1",
            event_id="unrelated", actor_id="actor-A", posting_date="2026-08-25",
            source=source,
            lines=(JournalLine(mapping(party="supplier-A").bank, debit_rial=101),
                   JournalLine(mapping(party="supplier-A").ap, credit_rial=101)),
            chart=chart(), scopes=s, money_policy=CompanyMoneyPolicy("co-A"),
            expected_revision=jrn.revision, today=TODAY,
        )
        self.reject(lambda: proposal(chq, forged, "event-2"), ChequeGLConflict)

    def test_different_journal_event_id_same_cheque_source_rejected(self):
        chq = register()
        s = scope_for(chq)
        jrn = journal_state()
        source = JournalSource("independent", cheque_journal_source_id(
            "co-A", "check-1", "event-1"))
        jrn = post_journal(
            jrn, company_id="co-A", fiscal_period_id="FY1",
            event_id="wrong-event", actor_id="actor-A", posting_date="2026-05-22",
            source=source,
            lines=(JournalLine(mapping().in_hand, debit_rial=101),
                   JournalLine(mapping().ar, credit_rial=101)),
            chart=chart(), scopes=s, money_policy=CompanyMoneyPolicy("co-A"),
            expected_revision=jrn.revision, today=TODAY,
        )
        self.reject(lambda: proposal(chq, jrn, "event-1"), ChequeGLConflict)

    def test_stable_business_id_changes_by_company_cheque_event(self):
        id1 = cheque_journal_source_id("co-A", "check-1", "event-1")
        self.assertEqual(id1, cheque_journal_source_id("co-A", "check-1", "event-1"))
        self.assertNotEqual(id1, cheque_journal_source_id("co-B", "check-1", "event-1"))
        self.assertNotEqual(id1, cheque_journal_source_id("co-A", "check-2", "event-1"))
        self.assertNotEqual(id1, cheque_journal_source_id("co-A", "check-1", "event-2"))
        self.assertLessEqual(len(id1), 96)

    def test_cross_company_mapping_chart_policy_journal_fails(self):
        chq = register()
        jrn = journal_state()
        self.reject(lambda: proposal(chq, jrn, "event-1", mappings=mapping("co-B")))
        self.reject(lambda: proposal(chq, jrn, "event-1", accounts=chart("co-B")))
        self.reject(lambda: proposal(chq, jrn, "event-1",
                                     money=CompanyMoneyPolicy("co-B")))
        self.reject(lambda: proposal(chq, journal_state("co-B"), "event-1"))
        self.reject(lambda: proposal(chq, jrn, "event-1",
                                     verified=scope_for(chq, "co-B")))

    def test_missing_verified_source_or_party_refused(self):
        chq = register()
        empty = VerifiedScopes(party_ids=frozenset({"customer-A"}))
        self.reject(lambda: proposal(chq, journal_state(), "event-1",
                                     verified=empty))
        no_party = VerifiedScopes(independent_source_scopes=scope_for(
            chq).independent_source_scopes)
        self.reject(lambda: proposal(chq, journal_state(), "event-1",
                                     verified=no_party))

    def test_unavailable_group_frozen_archived_or_wrong_kind_account_rejected(self):
        chq = register()
        for code in ("10", "200101", "199999"):
            with self.subTest(code=code):
                bad = replace(mapping(), in_hand=PostingReference("co-A", code))
                self.reject(lambda m=bad: proposal(chq, journal_state(),
                                                   "event-1", mappings=m))
        original = chart()
        accounts = tuple(replace(a, frozen=True) if a.code == "100101"
                         else a for a in original.accounts)
        self.reject(lambda: proposal(chq, journal_state(), "event-1",
                                     accounts=replace(original, accounts=accounts)))
        archived = tuple(replace(a, active=False, archived=True)
                         if a.code == "100101" else a for a in original.accounts)
        self.reject(lambda: proposal(chq, journal_state(), "event-1",
                                     accounts=replace(original, accounts=archived)))

    def test_reject_self_canceling_transfer_mapping(self):
        chq = register()
        duplicated = replace(mapping(), ar=mapping().in_hand)
        self.reject(lambda: proposal(chq, journal_state(), "event-1",
                                     mappings=duplicated))

    def test_party_reference_must_be_bound_to_instrument(self):
        chq = register()
        spoof = replace(mapping(), party_id="customer-B")
        self.reject(lambda: proposal(chq, journal_state(), "event-1",
                                     mappings=spoof))
        spoof = replace(mapping(), ar=PostingReference(
            "co-A", "100105", party_id="customer-B"))
        self.reject(lambda: proposal(chq, journal_state(), "event-1",
                                     mappings=spoof))

    def test_bank_must_match_issued_or_deposited_instrument(self):
        payable = register("PAYABLE")
        self.reject(lambda: proposal(payable, journal_state(), "event-1",
                                     mappings=mapping(
                                         party="supplier-A", account="own-B")))
        receivable = advance(register(), "DEPOSIT",
                             bank="bank-A", account="own-A")
        jrn, _ = post(receivable, journal_state(), "event-1")
        self.reject(lambda: proposal(receivable, jrn, "event-2",
                                     mappings=mapping(bank="bank-B", account="own-B")))

    def test_bounded_money_requires_integer_and_policy_ceiling(self):
        chq = register(amount=MAX_RIAL)
        self.assertEqual(proposal(chq, journal_state(), "event-1").amount_rial,
                         MAX_RIAL)
        self.reject(lambda: proposal(chq, journal_state(), "event-1",
                                     money=CompanyMoneyPolicy("co-A", max_abs_rial=100)))

    def test_period_and_calendar_attestation_mismatch_fails_shut(self):
        chq = register()
        base = context(chq, "event-1")
        self.reject(lambda: proposal(chq, journal_state(), "event-1",
                                     ctx=replace(base, gregorian_posting_date="2026-01-01")))
        self.reject(lambda: proposal(chq, journal_state(), "event-1",
                                     ctx=replace(base, gregorian_posting_date="2027-03-21")))
        self.reject(lambda: proposal(chq, journal_state(), "event-1",
                                     ctx=replace(base, gregorian_posting_date="2026-02-30")))
        self.reject(lambda: proposal(chq, journal_state(), "event-1",
                                     ctx=replace(base, fiscal_period_id="FY2")))
        self.reject(lambda: proposal(chq, journal_state(), "event-1",
                                     ctx=replace(base, jalali_event_date="1405-04-01")))
        self.reject(lambda: proposal(chq, journal_state(), "event-1",
                                     ctx=replace(base, actor_id="unknown")))
        self.reject(lambda: proposal(chq, journal_state(), "event-1",
                                     ctx=replace(base, prior_ar_ap_accrued=False)))

    def test_closed_journal_fiscal_period_prevents_new_cheque_posting(self):
        chq = register()
        old = journal_state()
        closed = close_fiscal_period(
            old, company_id="co-A", fiscal_period_id="FY1",
            event_id="closing-1", actor_id="actor-A",
            closing_date="2026-09-23", expected_revision=old.revision,
            today=TODAY,
        )
        self.reject(lambda: proposal(chq, closed, "event-1"))

    def test_immutable_proposal_and_tampering_denied_at_post(self):
        chq = register()
        jrn = journal_state()
        p = proposal(chq, jrn, "event-1")
        with self.assertRaises(FrozenInstanceError):
            p.amount_rial = 5
        malformed = replace(p, lines=tuple(reversed(p.lines)))
        self.reject(lambda: post_cheque_journal(
            chq, jrn, proposal=malformed, mapping=mapping(),
            chart=chart(), scopes=scope_for(chq),
            money_policy=CompanyMoneyPolicy("co-A"),
            context=context(chq, "event-1"), today=TODAY,
            expected_journal_revision=jrn.revision), ChequeGLConflict)

    def test_stale_revision_rejected_and_retry_is_exact_noop(self):
        chq = register()
        old = journal_state()
        jrn, _ = post(chq, old, "event-1")
        ctx = context(chq, "event-1")
        original = proposal(chq, old, "event-1")
        self.reject(lambda: post_cheque_journal(
            chq, jrn, proposal=original, mapping=mapping(),
            chart=chart(), scopes=scope_for(chq),
            money_policy=CompanyMoneyPolicy("co-A"),
            context=ctx, today=TODAY,
            expected_journal_revision=old.revision), ChequeGLConflict)
        retried, newer = post(chq, jrn, "event-1")
        self.assertIs(retried, jrn)
        self.assertEqual(newer.event_id, jrn.events[0].event_id)

    def test_unknown_cheque_event_does_not_create_journal(self):
        chq = register()
        self.reject(lambda: propose_cheque_journal(
            chq, journal_state(), cheque_event_id="fake-event",
            mapping=mapping(), chart=chart(), scopes=scope_for(chq),
            money_policy=CompanyMoneyPolicy("co-A"),
            context=context(chq, "event-1"), today=TODAY))
        self.assertEqual(len(journal_state().events), 0)

    def test_prior_stage_tampering_in_real_ledger_is_detected(self):
        chq = advance(register(), "DEPOSIT",
                      bank="bank-A", account="own-A")
        old = journal_state()
        source = JournalSource("independent", cheque_journal_source_id(
            "co-A", "check-1", "event-1"))
        forged = post_journal(
            old, company_id="co-A", fiscal_period_id="FY1",
            event_id="chq." + source.source_id.split(".")[-1],
            actor_id="actor-A", posting_date="2026-05-22",
            source=source,
            lines=(JournalLine(mapping().bank, debit_rial=101),
                   JournalLine(mapping().ar, credit_rial=101)),
            chart=chart(), scopes=scope_for(chq),
            money_policy=CompanyMoneyPolicy("co-A"),
            expected_revision=old.revision, today=TODAY,
        )
        self.reject(lambda: proposal(chq, forged, "event-2"),
                    ChequeGLConflict)


if __name__ == "__main__":
    unittest.main()
