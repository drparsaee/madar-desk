"""Adversarial, synthetic and IO-free cheque lifecycle tests."""
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ir_treasury_cheques as cheque
from ir_treasury_cheques import (
    ChequeBusinessSource, ChequeCommand, ChequeConflict, ChequeError,
    ChequeInstrument, ChequePeriod, VerifiedChequeRefs,
    append_cheque_event, new_cheque_state, overdue_cheques, replay_cheques,
)
from money_policy import MAX_RIAL


def periods(company="co-A"):
    return (
        ChequePeriod(company, "FY1", "1405-01-01", "1405-06-31"),
        ChequePeriod(company, "FY2", "1405-07-01", "1405-12-29"),
    )


def state(company="co-A"):
    return new_cheque_state(company, periods(company))


def scopes(company="co-A", *, closed=()):
    return VerifiedChequeRefs(
        company_id=company,
        party_ids=frozenset({"customer-A", "supplier-A", "supplier-B"}),
        bank_ids=frozenset({"bank-A", "bank-B"}),
        own_bank_accounts=frozenset({
            ("bank-A", "ours-A"), ("bank-B", "ours-B")}),
        supplier_party_ids=frozenset({"supplier-A", "supplier-B"}),
        closed_period_ids=frozenset(closed),
    )


def instrument(*, company="co-A", cheque_id="cheque-1", instrument_id="paper-1",
               direction="RECEIVABLE", amount=101, party=None,
               bank=None, drawer=None, maturity="1405-06-01"):
    return ChequeInstrument(
        company, cheque_id, instrument_id, direction, amount,
        bank or ("bank-B" if direction == "RECEIVABLE" else "bank-A"),
        drawer or ("external-A" if direction == "RECEIVABLE" else "ours-A"),
        party or ("customer-A" if direction == "RECEIVABLE" else "supplier-A"),
        maturity)


def command(action="RECEIVE", *, company="co-A", event="event-1",
            cheque_id="cheque-1", kind="invoice", source="invoice-1",
            date="1405-03-01", period="FY1", ins=None, bank="", account="",
            supplier="", target="", reason=""):
    return ChequeCommand(
        event_id=event, company_id=company, fiscal_period_id=period,
        actor_id="trusted-actor", event_date=date, cheque_id=cheque_id,
        action=action, source=ChequeBusinessSource(kind, source),
        instrument=ins, bank_id=bank, bank_account_id=account,
        supplier_party_id=supplier, reverses_event_id=target, reason=reason)


def apply(old, cmd, *, trusted=None, rev=None, today="1405-11-01"):
    return append_cheque_event(
        old, cmd, scopes=trusted or scopes(old.company_id),
        expected_revision=old.revision if rev is None else rev, today=today)


def registered(direction="RECEIVABLE", *, company="co-A", amount=101,
               cheque_id="cheque-1", instrument_id="paper-1"):
    old = state(company)
    action = "RECEIVE" if direction == "RECEIVABLE" else "ISSUE"
    cmd = command(action, company=company, cheque_id=cheque_id,
                  ins=instrument(company=company, cheque_id=cheque_id,
                                 instrument_id=instrument_id,
                                 direction=direction, amount=amount))
    return apply(old, cmd)


def move(old, action, *, event="event-2", date="1405-06-03",
         period="FY1", source=None, kind="bank", cheque_id="cheque-1",
         bank="", account="", supplier="", target="", reason=""):
    cmd = command(action, company=old.company_id, cheque_id=cheque_id,
                  event=event, date=date, period=period, source=source or event,
                  kind=kind, bank=bank, account=account, supplier=supplier,
                  target=target, reason=reason)
    return apply(old, cmd)


class ChequeDomainTests(unittest.TestCase):
    def reject(self, callback, error=(ChequeError, ValueError)):
        with self.assertRaises(error):
            callback()

    def test_registration_receivable_and_one_rial_exact(self):
        s = registered(amount=1)
        r = replay_cheques(s)
        self.assertEqual(r.currency, "RIAL")
        self.assertEqual(r.calendar, "JALALI")
        self.assertEqual(len(r.positions), 1)
        self.assertEqual(r.positions[0].status, "RECEIVED")
        self.assertEqual(r.intents[0].amount_rial, 1)
        self.assertEqual(r.intents[0].cash_effect, "NONE")
        self.assertEqual(len(s.events[0].event_hash), 64)

    def test_payable_issue_present_clear_only_then_cash_credit(self):
        s = registered("PAYABLE")
        s = move(s, "PRESENT")
        s = move(s, "CLEAR", event="event-3", source="bank-cleared",
                 date="1405-07-05", period="FY2")
        r = replay_cheques(s)
        self.assertEqual(r.positions[0].status, "CLEARED")
        self.assertEqual([i.cash_effect for i in r.intents],
                         ["NONE", "NONE", "CREDIT_BANK"])
        self.assertEqual(r.positions[0].cleared_date, "1405-07-05")
        self.reject(lambda: move(s, "CLEAR", event="event-4"))
        self.reject(lambda: move(s, "BOUNCE", event="event-4"))
        self.assertEqual(overdue_cheques(s, today="1405-10-01"), ())

    def test_receivable_deposit_clear_cash_debit_only_at_clear(self):
        s = registered()
        s = move(s, "DEPOSIT", bank="bank-A", account="ours-A")
        intermediate = replay_cheques(s)
        self.assertEqual(intermediate.positions[0].status, "DEPOSITED")
        self.assertTrue(all(i.cash_effect == "NONE" for i in intermediate.intents))
        self.assertFalse(intermediate.intents[1].requires_accounting_review)
        s = move(s, "CLEAR", event="event-3", source="bank-cleared",
                 date="1405-07-02", period="FY2")
        r = replay_cheques(s)
        self.assertEqual(sum(i.cash_effect == "DEBIT_BANK" for i in r.intents), 1)
        self.assertEqual(r.positions[0].status, "CLEARED")
        self.assertEqual(r.intents[-1].amount_rial, 101)

    def test_endorsement_only_to_verified_supplier_and_terminal_return(self):
        s = registered()
        s = move(s, "ENDORSE", date="1405-04-01", kind="purchase",
                 supplier="supplier-B")
        r = replay_cheques(s)
        self.assertEqual(r.positions[0].status, "ENDORSED")
        self.assertEqual(r.positions[0].endorsed_supplier_id, "supplier-B")
        self.assertEqual(r.intents[-1].cash_effect, "NONE")
        self.reject(lambda: move(s, "DEPOSIT", event="event-3",
                                 bank="bank-A", account="ours-A"))
        self.reject(lambda: move(s, "CLEAR", event="event-3"))
        s = move(s, "RETURN", event="event-3", date="1405-04-04",
                 reason="Supplier returned the endorsed instrument")
        self.assertEqual(replay_cheques(s).positions[0].status, "RETURNED")
        self.assertEqual(overdue_cheques(s, today="1405-07-01"), ())

    def test_bounce_then_redeposit_clear_has_one_cash_recognition(self):
        s = registered()
        s = move(s, "DEPOSIT", bank="bank-A", account="ours-A")
        s = move(s, "BOUNCE", event="event-3", date="1405-06-04",
                 reason="Bank returned unpaid")
        self.assertEqual(replay_cheques(s).positions[0].status, "BOUNCED")
        self.assertTrue(all(i.cash_effect == "NONE" for i in replay_cheques(s).intents))
        s = move(s, "REDEPOSIT", event="event-4", date="1405-06-05",
                 bank="bank-A", account="ours-A")
        s = move(s, "CLEAR", event="event-5", date="1405-07-01", period="FY2")
        r = replay_cheques(s)
        self.assertEqual(r.positions[0].status, "CLEARED")
        self.assertEqual(sum(i.cash_effect != "NONE" for i in r.intents), 1)

    def test_payable_bounce_represent_and_return(self):
        s = registered("PAYABLE")
        s = move(s, "PRESENT")
        s = move(s, "BOUNCE", event="event-3", reason="Insufficient funds")
        s = move(s, "REPRESENT", event="event-4")
        s = move(s, "BOUNCE", event="event-5", reason="Bank refuses")
        s = move(s, "RETURN", event="event-6", reason="Holder surrendered cheque")
        r = replay_cheques(s)
        self.assertEqual(r.positions[0].status, "RETURNED")
        self.assertTrue(all(i.cash_effect == "NONE" for i in r.intents))

    def test_cancel_only_unpresented_payable_with_reason(self):
        p = registered("PAYABLE")
        self.reject(lambda: move(p, "CANCEL"))
        cancelled = move(p, "CANCEL", reason="Original physically voided")
        self.assertEqual(replay_cheques(cancelled).positions[0].status, "CANCELLED")
        self.reject(lambda: move(cancelled, "PRESENT", event="event-3"))
        self.reject(lambda: move(registered(), "CANCEL",
                                 reason="Cannot cancel other party paper"))
        presented = move(p, "PRESENT")
        self.reject(lambda: move(presented, "CANCEL", event="event-3",
                                 reason="Cannot void presented instrument"))

    def test_reverse_last_deposit_restores_receivable_without_cash(self):
        s = registered()
        s = move(s, "DEPOSIT", bank="bank-A", account="ours-A")
        reversed_s = move(s, "REVERSE", event="event-3", date="1405-06-05",
                          target="event-2", reason="Bank confirmed withdrawal")
        r = replay_cheques(reversed_s)
        self.assertEqual(r.positions[0].status, "RECEIVED")
        self.assertEqual(r.reversed_event_ids, frozenset({"event-2"}))
        self.assertEqual([i.cash_effect for i in r.intents], ["NONE"] * 3)
        self.reject(lambda: move(reversed_s, "REVERSE", event="event-4",
                                 target="event-2", reason="Again"))
        self.reject(lambda: move(reversed_s, "REVERSE", event="event-4",
                                 target="event-1", reason="Undo registration"))
        self.assertEqual(replay_cheques(s).positions[0].status, "DEPOSITED")

    def test_reverse_bounce_requires_latest_and_preserves_strict_rules(self):
        s = move(registered(), "DEPOSIT", bank="bank-A", account="ours-A")
        s = move(s, "BOUNCE", event="event-3", reason="Bank bounce")
        s = move(s, "REVERSE", event="event-4", target="event-3",
                 reason="Formal bounce correction")
        self.assertEqual(replay_cheques(s).positions[0].status, "DEPOSITED")
        # Active movement is again deposit; bank must separately approve withdrawal.
        s = move(s, "REVERSE", event="event-5", target="event-2",
                 reason="Withdrawal confirmed")
        self.assertEqual(replay_cheques(s).positions[0].status, "RECEIVED")
        self.assertEqual(replay_cheques(s).reversed_event_ids,
                         frozenset({"event-2", "event-3"}))

    def test_open_period_can_reverse_prior_period_bank_action_after_close(self):
        s = move(registered(), "DEPOSIT", bank="bank-A", account="ours-A")
        reversal = command("REVERSE", event="event-3",
                           source="bank-reversal-3", kind="bank",
                           date="1405-07-03", period="FY2",
                           target="event-2", reason="Confirmed deposit reversal")
        saved = apply(s, reversal, trusted=scopes(closed={"FY1"}))
        self.assertEqual(replay_cheques(saved).positions[0].status, "RECEIVED")
        self.assertEqual(saved.events[0], s.events[0])
        self.assertEqual(saved.events[1], s.events[1])

    def test_cannot_reverse_cleared_endorsed_returned_or_cancelled(self):
        receivable = move(registered(), "DEPOSIT", bank="bank-A", account="ours-A")
        cleared = move(receivable, "CLEAR", event="event-3")
        self.reject(lambda: move(cleared, "REVERSE", event="event-4",
                                 target="event-3", reason="No cash reversal here"))
        endorsed = move(registered(), "ENDORSE", supplier="supplier-B",
                        date="1405-04-01")
        self.reject(lambda: move(endorsed, "REVERSE", event="event-3",
                                 target="event-2", reason="Needs return workflow"))

    def test_event_retry_exact_is_noop_and_conflicting_payload_fails(self):
        s = registered()
        same_cmd = s.events[0].command
        self.assertIs(apply(s, same_cmd), s)
        altered = replace(same_cmd, actor_id="another-actor")
        self.reject(lambda: apply(s, altered), ChequeConflict)

    def test_stale_revision_rejected_even_for_exact_retry(self):
        old = state()
        s = registered()
        self.reject(lambda: apply(s, s.events[0].command, rev=old.revision),
                    ChequeConflict)

    def test_unique_source_even_when_new_event_id_is_used(self):
        s = registered()
        duplicate_source = command("RECEIVE", event="event-2",
                                   cheque_id="cheque-2",
                                   ins=instrument(cheque_id="cheque-2",
                                                  instrument_id="paper-2"))
        self.reject(lambda: apply(s, duplicate_source), ChequeConflict)
        s = move(s, "DEPOSIT", bank="bank-A", account="ours-A")
        self.reject(lambda: move(s, "BOUNCE", event="event-3",
                                 source="event-2", reason="Another source reuse"),
                    ChequeConflict)

    def test_duplicate_paper_rejected_even_across_opposite_directions(self):
        s = registered()
        repeated_paper = command(
            "ISSUE", event="event-2", source="invoice-2", kind="purchase",
            cheque_id="cheque-2", ins=instrument(
                cheque_id="cheque-2", direction="PAYABLE"))
        self.reject(lambda: apply(s, repeated_paper), ChequeConflict)
        self.assertEqual(len(s.events), 1)

    def test_two_companies_same_identifier_independent_and_spoof_rejected(self):
        a, b = registered(company="co-A"), registered(company="co-B")
        self.assertNotEqual(a.revision, b.revision)
        self.assertEqual(len(replay_cheques(a).positions), 1)
        self.assertEqual(len(replay_cheques(b).positions), 1)
        foreign = command("RECEIVE", company="co-B", ins=instrument(company="co-B"))
        self.reject(lambda: apply(state("co-A"), foreign))
        self.reject(lambda: apply(state(), state_command(), trusted=scopes("co-B")))

    def test_party_bank_and_own_account_scope_refusals(self):
        self.reject(lambda: apply(state(), command("RECEIVE", ins=instrument(
            party="forged-party"))))
        self.reject(lambda: apply(state(), command("RECEIVE", ins=instrument(
            bank="foreign-bank"))))
        self.reject(lambda: apply(state(), command("ISSUE", ins=instrument(
            direction="PAYABLE", drawer="non-company-account"))))
        self.reject(lambda: move(registered(), "DEPOSIT",
                                 bank="bank-B", account="foreign-account"))
        self.reject(lambda: move(registered(), "ENDORSE",
                                 supplier="customer-A", date="1405-04-01"))

    def test_unsupported_source_and_unbounded_fields_refused(self):
        self.reject(lambda: ChequeBusinessSource("unknown", "abc"))
        self.reject(lambda: ChequeBusinessSource("invoice", "bad id"))
        self.reject(lambda: ChequeBusinessSource("invoice", ""))
        self.reject(lambda: command("DEPOSIT"))
        self.reject(lambda: command("ENDORSE"))
        self.reject(lambda: command("REVERSE", target="event-1"))
        self.reject(lambda: command("CANCEL"))
        self.reject(lambda: command("CLEAR", bank="bank-A", account="ours-A"))
        self.reject(lambda: VerifiedChequeRefs(
            "co-A", frozenset({"customer-A"}), frozenset({"bank-A"}),
            frozenset({("bank-B", "ours-B")})))

    def test_reject_float_bool_zero_negative_and_overflow_amount(self):
        for invalid in (0, -1, 1.0, True, MAX_RIAL + 1):
            with self.subTest(amount=invalid):
                self.reject(lambda v=invalid: instrument(amount=v), ChequeError)
        largest = registered(amount=MAX_RIAL)
        self.assertEqual(replay_cheques(largest).positions[0].instrument.amount_rial,
                         MAX_RIAL)

    def test_persian_date_is_explicit_not_automatically_converted(self):
        for bad in ("2026-10-22", "۱۴۰۵-۰۷-۳۰", "1405/07/30",
                    "1405-07-31", "1405-06-32", "1404-12-30", "1405-12-30",
                    "1405-00-01", "1405-01-00", "1405-7-01"):
            with self.subTest(bad=bad):
                self.reject(lambda day=bad: command(date=day, ins=instrument()))
        self.assertEqual(instrument().maturity_date, "1405-06-01")
        self.assertEqual(cheque._date("1403-12-30"), "1403-12-30")
        self.reject(lambda: ChequePeriod("co-A", "P", "1405-07-01", "1405-06-31"))

    def test_maturity_and_historical_order_are_guarded(self):
        s = registered()
        self.reject(lambda: move(s, "DEPOSIT", date="1405-05-30",
                                 bank="bank-A", account="ours-A"))
        self.reject(lambda: move(s, "PRESENT"))
        s = move(s, "DEPOSIT", bank="bank-A", account="ours-A")
        self.reject(lambda: move(s, "CLEAR", event="event-3",
                                 date="1405-05-30"))
        self.reject(lambda: apply(s, command(
            "BOUNCE", event="event-3", date="1405-06-01",
            reason="Historical backdate", source="bank-3")))

    def test_future_actions_closed_or_nonexisting_period_rejected(self):
        s = registered()
        self.reject(lambda: move(s, "DEPOSIT", date="1405-12-01",
                                 period="FY2", bank="bank-A", account="ours-A",
                                 event="event-3"))
        c = command("DEPOSIT", event="event-2", date="1405-06-02",
                    bank="bank-A", account="ours-A")
        self.reject(lambda: apply(s, c, trusted=scopes(closed={"FY1"})))
        self.reject(lambda: apply(s, replace(c, fiscal_period_id="unknown")))
        self.reject(lambda: new_cheque_state("co-A", (periods()[0], periods()[0])))

    def test_overdue_query_is_today_parameterized_sorted_and_excludes_terminal(self):
        s = registered()
        new = command("ISSUE", event="event-2", source="purchase-2", kind="purchase",
                      cheque_id="cheque-2", ins=instrument(
                          cheque_id="cheque-2", instrument_id="paper-2",
                          direction="PAYABLE", maturity="1405-05-01"))
        s = apply(s, new)
        self.assertEqual([p.instrument.cheque_id for p in overdue_cheques(
            s, today="1405-07-01")], ["cheque-2", "cheque-1"])
        self.assertEqual(overdue_cheques(s, today="1405-05-01"), ())
        s = move(s, "CANCEL", event="event-3", cheque_id="cheque-2",
                 source="cancel-doc-2", date="1405-05-02",
                 reason="Recovered original document")
        self.assertEqual([p.instrument.cheque_id for p in overdue_cheques(
            s, today="1405-07-01")], ["cheque-1"])

    def test_late_registration_of_already_overdue_cheque_is_allowed(self):
        old = state()
        late = command("RECEIVE", ins=instrument(maturity="1405-02-01"),
                       date="1405-03-01")
        s = apply(old, late)
        self.assertEqual(overdue_cheques(s, today="1405-03-01")[0].status, "RECEIVED")
        self.reject(lambda: move(s, "DEPOSIT", event="event-2",
                                 date="1405-02-02", bank="bank-A",
                                 account="ours-A"))

    def test_history_tampering_detected_even_when_prior_hash_valid(self):
        s = registered()
        event = s.events[0]
        changed = replace(event.command, actor_id="forged-admin")
        self.reject(lambda: replay_cheques(replace(
            s, events=(replace(event, command=changed),))))
        fake = replace(event, command=changed,
                       command_digest=cheque._command_digest(changed),
                       event_hash=cheque._event_hash(changed, event.previous_hash))
        # A cryptographic hash alone does not establish an authentic authority;
        # host needs anchored head hash / ACL. Recomputed valid event can replay.
        forged = replace(s, events=(fake,))
        self.assertEqual(replay_cheques(forged).positions[0].status, "RECEIVED")
        self.assertNotEqual(forged.revision, s.revision)

    def test_valid_hash_with_illegal_transition_is_still_rejected(self):
        s = registered()
        impossible = command("CLEAR", event="event-2", source="illegal-clear",
                             date="1405-06-03")
        old = s.events[-1].event_hash
        fake = cheque.ChequeEvent(impossible, cheque._command_digest(impossible),
                                  old, cheque._event_hash(impossible, old))
        self.reject(lambda: replay_cheques(replace(s, events=s.events + (fake,))))

    def test_history_rejects_duplicate_source_with_completely_recomputed_hash(self):
        s = registered()
        duplicated_source = command("ISSUE", event="event-2", source="invoice-1",
                                    cheque_id="cheque-2",
                                    ins=instrument(cheque_id="cheque-2",
                                                   instrument_id="paper-2",
                                                   direction="PAYABLE"))
        old = s.events[-1].event_hash
        forged = cheque.ChequeEvent(
            duplicated_source, cheque._command_digest(duplicated_source),
            old, cheque._event_hash(duplicated_source, old))
        self.reject(lambda: replay_cheques(
            replace(s, events=s.events + (forged,))), ChequeConflict)

    def test_hash_chain_detects_out_of_order_and_changed_predecessor(self):
        s = move(registered(), "DEPOSIT", bank="bank-A", account="ours-A")
        self.reject(lambda: replay_cheques(
            replace(s, events=(s.events[1], s.events[0]))))
        altered = replace(s.events[1], previous_hash="0" * 64)
        self.reject(lambda: replay_cheques(
            replace(s, events=(s.events[0], altered))))
        self.reject(lambda: replay_cheques(replace(s, currency="TOMAN")))
        self.reject(lambda: replay_cheques(replace(s, calendar="GREGORIAN")))

    def test_immutable_history_and_no_mutation_after_failure(self):
        s = registered()
        with self.assertRaises(FrozenInstanceError):
            s.events[0].command.action = "CLEAR"
        with self.assertRaises(FrozenInstanceError):
            s.events = ()
        self.reject(lambda: move(s, "BOUNCE", reason="No deposit"))
        self.assertEqual(len(s.events), 1)
        self.assertEqual(replay_cheques(s).positions[0].status, "RECEIVED")


def state_command():
    return command("RECEIVE", ins=instrument())


if __name__ == "__main__":
    unittest.main()
