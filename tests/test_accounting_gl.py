"""M08 GL kernel tests: synthetic in-memory data only, no DB/APPDATA/accounts."""

from copy import deepcopy
from datetime import datetime
import hashlib
import json
import unittest

from accounting_gl import (
    MAX_TOMAN, apply_gl_command, empty_gl_state, gl_view,
    trial_balance, validate_gl_state,
)


NOW = "2026-10-21T16:00:00+03:30"
DAY = "2026-10-21"
ADMIN = {"root": {"username": "root", "role": "admin"}}
ACCOUNTS = {
    **ADMIN,
    "editor": {"username": "editor", "role": "editor", "financeEdit": True},
    "reader": {"username": "reader", "role": "viewer", "financeView": True},
}


def digest(value):
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                     separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def recalc_chain(snapshot):
    for i, entry in enumerate(snapshot["events"]):
        entry["prevHash"] = ("0" * 64 if i == 0 else snapshot["events"][i - 1]["hash"])
        entry["fingerprint"] = digest([entry["actor"], entry["command"]])
        entry["hash"] = digest({k: v for k, v in entry.items() if k != "hash"})


class M08GLTests(unittest.TestCase):
    def setUp(self):
        self.state = empty_gl_state()
        self.counter = 0

    def apply(self, action, *, actor="root", now=NOW, **fields):
        self.counter += 1
        result = apply_gl_command(
            self.state,
            {"type": action, "eventId": f"ev-{self.counter}", **fields},
            actor=actor, accounts=ACCOUNTS, now=now)
        self.state = result["state"]
        return result

    def account(self, aid, kind):
        return self.apply("account.create", accountId=aid, name="Account " + aid, kind=kind)

    def chart(self):
        self.account("cash", "asset")
        self.account("receivable", "asset")
        self.account("payable", "liability")
        self.account("owner", "equity")
        self.account("sales", "revenue")
        self.account("expenses", "expense")

    def post(self, journal_id="J1", amount=500, *, date=DAY):
        return self.apply("journal.post", journalId=journal_id,
                          postingDate=date, description="Explicit owner deposit",
                          lines=[
                              {"accountId": "cash", "debit": amount, "credit": 0},
                              {"accountId": "owner", "debit": 0, "credit": amount}])

    def test_empty_valid_strict_and_detached_view(self):
        self.assertTrue(validate_gl_state(self.state))
        original = deepcopy(self.state)
        view = gl_view(self.state, actor="root", accounts=ACCOUNTS)
        self.assertEqual(view["journals"], [])
        self.assertEqual(view["trialBalance"]["totals"]["debitBalance"], 0)
        view["accounts"].append({"id": "fake"})
        self.assertEqual(self.state, original)
        self.assertEqual(json.loads(json.dumps(self.state)), self.state)

    def test_all_account_categories_normal_balance_and_exact_journal(self):
        self.chart()
        self.assertEqual(len(gl_view(self.state, actor="root", accounts=ACCOUNTS)["accounts"]), 6)
        self.post()
        balances = trial_balance(self.state, actor="root", accounts=ACCOUNTS)
        indexed = {item["id"]: item for item in balances["accounts"]}
        self.assertEqual(indexed["cash"]["normalSide"], "debit")
        self.assertEqual(indexed["payable"]["normalSide"], "credit")
        self.assertEqual(indexed["expenses"]["normalSide"], "debit")
        self.assertEqual(indexed["sales"]["normalSide"], "credit")
        self.assertEqual(indexed["cash"]["normalBalance"], 500)
        self.assertEqual(indexed["owner"]["normalBalance"], 500)
        self.assertEqual(balances["totals"], {
            "debitTurnover": 500, "creditTurnover": 500,
            "debitBalance": 500, "creditBalance": 500})
        self.assertTrue(validate_gl_state(self.state))

    def test_purchase_payable_and_receivable_examples_are_balanced(self):
        self.chart()
        self.apply("journal.post", journalId="P1", postingDate=DAY,
                   description="Supplier purchase on credit",
                   lines=[{"accountId": "expenses", "debit": 120, "credit": 0},
                          {"accountId": "payable", "debit": 0, "credit": 120}])
        self.apply("journal.post", journalId="S1", postingDate=DAY,
                   description="Sale earned not collected",
                   lines=[{"accountId": "receivable", "debit": 200, "credit": 0},
                          {"accountId": "sales", "debit": 0, "credit": 200}])
        amounts = {r["id"]: r["normalBalance"] for r in
                   trial_balance(self.state, actor="root", accounts=ACCOUNTS)["accounts"]}
        self.assertEqual(amounts["payable"], 120)
        self.assertEqual(amounts["expenses"], 120)
        self.assertEqual(amounts["receivable"], 200)
        self.assertEqual(amounts["sales"], 200)

    def test_immutable_one_time_reversal_swaps_sides_and_keeps_source(self):
        self.chart()
        self.post()
        posted = deepcopy(self.state["events"][-1])
        reversed_result = self.apply("journal.reverse", journalId="R1",
                                     reversesJournalId="J1", postingDate=DAY,
                                     reason="Correction approved by finance admin")
        self.assertEqual(self.state["events"][-2], posted)
        self.assertEqual(reversed_result["result"]["reversesJournalId"], "J1")
        view = gl_view(self.state, actor="root", accounts=ACCOUNTS)
        self.assertEqual(len(view["journals"]), 2)
        self.assertEqual(view["reversedJournalIds"], ["J1"])
        self.assertEqual(view["journals"][-1]["lines"][0],
                         {"accountId": "cash", "debit": 0, "credit": 500})
        trial = view["trialBalance"]["totals"]
        self.assertEqual(trial["debitBalance"], 0)
        self.assertEqual(trial["creditBalance"], 0)
        self.assertEqual(trial["debitTurnover"], 1000)
        self.assertEqual(trial["creditTurnover"], 1000)
        with self.assertRaisesRegex(ValueError, "already reversed"):
            self.apply("journal.reverse", journalId="R2",
                       reversesJournalId="J1", postingDate=DAY, reason="Repeated")
        with self.assertRaisesRegex(ValueError, "previously posted"):
            self.apply("journal.reverse", journalId="R3",
                       reversesJournalId="R1", postingDate=DAY, reason="No reversal of reversal")
        self.assertEqual(len(self.state["events"]), 8)

    def test_idempotency_exact_replay_returns_original_result_and_no_append(self):
        self.chart()
        command = {"type": "journal.post", "eventId": "posted-once",
                   "journalId": "exact", "postingDate": DAY,
                   "description": "Deposit", "lines": [
                       {"accountId": "cash", "debit": 200, "credit": 0},
                       {"accountId": "owner", "debit": 0, "credit": 200}]}
        one = apply_gl_command(self.state, command, actor="root", accounts=ACCOUNTS, now=NOW)
        original = deepcopy(one["state"])
        replay = apply_gl_command(one["state"], command, actor="root", accounts=ACCOUNTS,
                                  now="2026-10-22T09:20:30Z")
        self.assertFalse(replay["changed"])
        self.assertEqual(replay["result"], one["result"])
        self.assertEqual(replay["state"], original)
        self.assertEqual(one["state"], original)
        self.assertTrue(validate_gl_state(replay["state"]))

    def test_event_id_collision_rejects_different_amount_actor_or_type(self):
        self.chart()
        original = {"type": "journal.post", "eventId": "single",
                    "journalId": "one", "postingDate": DAY,
                    "description": "A", "lines": [
                        {"accountId": "cash", "debit": 1, "credit": 0},
                        {"accountId": "owner", "debit": 0, "credit": 1}]}
        out = apply_gl_command(self.state, original, actor="root", accounts=ACCOUNTS, now=NOW)
        baseline = deepcopy(out["state"])
        changed = deepcopy(original)
        changed["lines"][0]["debit"] = 2
        with self.assertRaisesRegex(ValueError, "Idempotency"):
            apply_gl_command(baseline, changed, actor="root", accounts=ACCOUNTS, now=NOW)
        with self.assertRaisesRegex(ValueError, "Idempotency"):
            apply_gl_command(baseline, original, actor="other",
                             accounts={"other": {"username": "other", "role": "admin"}}, now=NOW)
        self.assertEqual(out["state"], baseline)

    def test_acl_requires_current_authoritative_admin_even_for_replay(self):
        self.chart()
        c = {"type": "account.create", "eventId": "example",
             "accountId": "new", "name": "New", "kind": "asset"}
        out = apply_gl_command(self.state, c, actor="root", accounts=ACCOUNTS, now=NOW)
        for actor, records in [
            ("editor", ACCOUNTS), ("reader", ACCOUNTS),
            ("root", {"root": {"username": "root", "role": "viewer"}}),
            ("unknown", ACCOUNTS),
        ]:
            with self.subTest(actor=actor):
                with self.assertRaises(PermissionError):
                    apply_gl_command(out["state"], c, actor=actor, accounts=records, now=NOW)
                with self.assertRaises(PermissionError):
                    trial_balance(out["state"], actor=actor, accounts=records)
                with self.assertRaises(PermissionError):
                    gl_view(out["state"], actor=actor, accounts=records)
        with self.assertRaises(PermissionError):
            apply_gl_command(out["state"], c, actor="root", accounts=None, now=NOW)
        with self.assertRaises(ValueError):
            trial_balance(out["state"], actor="root",
                          accounts=[ACCOUNTS["root"], ACCOUNTS["root"]])

    def test_reject_unbalanced_and_same_side_or_duplicate_lines_no_mutation(self):
        self.chart()
        start = deepcopy(self.state)
        cases = [
            [{"accountId": "cash", "debit": 10, "credit": 0},
             {"accountId": "owner", "debit": 0, "credit": 9}],
            [{"accountId": "cash", "debit": 10, "credit": 1},
             {"accountId": "owner", "debit": 0, "credit": 10}],
            [{"accountId": "cash", "debit": 0, "credit": 0},
             {"accountId": "owner", "debit": 0, "credit": 10}],
            [{"accountId": "cash", "debit": 10, "credit": 0},
             {"accountId": "cash", "debit": 0, "credit": 10}],
            [{"accountId": "unknown", "debit": 10, "credit": 0},
             {"accountId": "owner", "debit": 0, "credit": 10}],
        ]
        for i, lines in enumerate(cases):
            with self.subTest(i=i), self.assertRaises(ValueError):
                self.apply("journal.post", journalId=f"bad-{i}", postingDate=DAY,
                           description="Unbalanced", lines=lines)
        self.assertEqual(self.state, start)

    def test_reject_invalid_money_overflows_and_implicit_float_rounding(self):
        self.chart()
        for index, money in enumerate((True, 0.5, -1, MAX_TOMAN + 1, "1", float("nan"), None)):
            lines = [{"accountId": "cash", "debit": money, "credit": 0},
                     {"accountId": "owner", "debit": 0, "credit": 10}]
            with self.subTest(value=str(money)), self.assertRaises(ValueError):
                self.apply("journal.post", journalId=f"amount-{index}",
                           postingDate=DAY, description="Bad amount", lines=lines)
        self.assertEqual(len(self.state["events"]), 6)
        with self.assertRaises(ValueError):
            self.post(amount=MAX_TOMAN + 1)

    def test_duplicate_chart_and_forged_field_are_rejected(self):
        self.account("cash", "asset")
        current = deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.account("cash", "asset")
        for record in (
            {"type": "account.create", "eventId": "bad-kind", "accountId": "bad",
             "name": "Bad", "kind": "other"},
            {"type": "account.create", "eventId": "bad-id", "accountId": "../bad",
             "name": "Bad", "kind": "asset"},
            {"type": "account.create", "eventId": "extra", "accountId": "ok",
             "name": "Valid", "kind": "asset", "password": "unauthorized"},
        ):
            with self.subTest(record=record), self.assertRaises(ValueError):
                apply_gl_command(self.state, record, actor="root",
                                 accounts=ACCOUNTS, now=NOW)
        self.assertEqual(self.state, current)

    def test_time_calendar_and_reversal_temporal_controls(self):
        self.chart()
        for bad in ("2026-02-30", "21-10-2026", "2026-13-01", "2026-10-22"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.post("bad-" + str(len(bad)), date=bad)
        with self.assertRaises(ValueError):
            apply_gl_command(self.state, {
                "type": "account.create", "eventId": "naive",
                "accountId": "x", "name": "X", "kind": "asset"},
                actor="root", accounts=ACCOUNTS, now="2026-10-21T10:00:00")
        self.apply("journal.post", journalId="late", postingDate="2026-10-21",
                   description="Real posting", lines=[
                       {"accountId": "cash", "debit": 50, "credit": 0},
                       {"accountId": "owner", "debit": 0, "credit": 50}])
        with self.assertRaisesRegex(ValueError, "predates"):
            self.apply("journal.reverse", journalId="early",
                       reversesJournalId="late", postingDate="2026-10-20",
                       reason="Cannot reverse yesterday")

    def test_hash_chain_and_sequence_detect_mutation(self):
        self.chart()
        self.post()
        original = deepcopy(self.state)
        changes = [
            lambda x: x["events"][0].__setitem__("seq", 2),
            lambda x: x["events"][0].__setitem__("actor", "someone"),
            lambda x: x["events"][-1]["command"]["lines"][0].__setitem__("debit", 25),
            lambda x: x["events"][-1].__setitem__("hash", "0" * 64),
            lambda x: x["events"][1].__setitem__("prevHash", "1" * 64),
            lambda x: x["events"].append(deepcopy(x["events"][-1])),
        ]
        for mutate in changes:
            altered = deepcopy(original)
            mutate(altered)
            with self.assertRaises(ValueError):
                validate_gl_state(altered)
        self.assertTrue(validate_gl_state(original))
        self.assertEqual(original, self.state)

    def test_rehashing_cannot_make_unbalanced_journal_semantically_valid(self):
        self.chart()
        self.post()
        forged = deepcopy(self.state)
        forged["events"][-1]["command"]["lines"][0]["debit"] = 490
        recalc_chain(forged)
        with self.assertRaisesRegex(ValueError, "Unbalanced"):
            validate_gl_state(forged)

    def test_rehashing_cannot_fake_reversal_result(self):
        self.chart()
        self.post()
        self.apply("journal.reverse", journalId="R1", reversesJournalId="J1",
                   postingDate=DAY, reason="Correction")
        forged = deepcopy(self.state)
        forged["events"][-1]["result"]["total"] = 1
        recalc_chain(forged)
        with self.assertRaisesRegex(ValueError, "outcome"):
            validate_gl_state(forged)

    def test_reversal_in_different_day_filters_trailing_balances(self):
        self.chart()
        self.apply("journal.post", journalId="backdated", postingDate="2026-10-18",
                   description="Prior invoice", lines=[
                       {"accountId": "receivable", "debit": 150, "credit": 0},
                       {"accountId": "sales", "debit": 0, "credit": 150}])
        self.apply("journal.reverse", journalId="reversed-today",
                   reversesJournalId="backdated", postingDate=DAY,
                   reason="Accrual corrected")
        before = trial_balance(self.state, actor="root", accounts=ACCOUNTS,
                               through_date="2026-10-20")
        after = trial_balance(self.state, actor="root", accounts=ACCOUNTS)
        self.assertEqual(before["totals"]["debitBalance"], 150)
        self.assertEqual(after["totals"]["debitBalance"], 0)
        with self.assertRaises(ValueError):
            trial_balance(self.state, actor="root", accounts=ACCOUNTS,
                          through_date="2026-02-30")

    def test_strict_version_currency_event_bounds_and_no_unsafe_extension(self):
        bad = [
            {**self.state, "schemaVersion": 2},
            {**self.state, "currency": "USD"},
            {**self.state, "accounts": {"income": "hidden"}},
            {**self.state, "events": {}},
            {**self.state, "events": [1]},
            {**self.state, "events": [float("nan")]},
        ]
        for source in bad:
            with self.subTest(source=str(source)[:100]), self.assertRaises(ValueError):
                validate_gl_state(source)

    def test_no_external_state_or_storage_modified_on_rejected_commands(self):
        self.chart()
        baseline = deepcopy(self.state)
        command = {"type": "journal.post", "eventId": "declined", "journalId": "x",
                   "postingDate": DAY, "description": "Invalid amount",
                   "lines": [{"accountId": "cash", "debit": 1, "credit": 0},
                             {"accountId": "owner", "debit": 0, "credit": 2}]}
        original_command = deepcopy(command)
        with self.assertRaises(ValueError):
            apply_gl_command(self.state, command, actor="root",
                             accounts=ACCOUNTS, now=NOW)
        self.assertEqual(command, original_command)
        self.assertEqual(self.state, baseline)


if __name__ == "__main__":
    unittest.main()
