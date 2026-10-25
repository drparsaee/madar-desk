"""Standalone finance domain: exact amounts, workflow, idempotency and ACL."""

from copy import deepcopy
import json
import unittest

from finance import (amount, apply_finance_command, card_cost_summary,
                     empty_finance_state, invoice_status, list_finance_ledger,
                     list_invoices, project_cost_summary, validate_finance_state)


NOW = "2026-10-20T16:00:00Z"
LATER = "2026-10-20T16:05:00Z"


class FinanceTests(unittest.TestCase):
    def setUp(self):
        self.state = empty_finance_state()
        self.projects = [{"id": "p1", "costEnabled": True, "price": 999999999},
                         {"id": "p2", "costEnabled": False, "price": 700000}]
        self.cards = [
            {"id": "c1", "projectId": "p1", "cost": 500,
             "costEnabled": None, "status": "active", "checklist": [
                 {"id": "x", "text": "Design", "cost": 100},
                 {"id": "y", "text": "Print", "cost": 200}]},
            {"id": "c2", "projectId": "p2", "status": "done", "cost": 400,
             "checklist": [{"id": "z", "cost": 90}]},
        ]
        self.accounts = {
            "admin": {"username": "admin", "role": "admin", "projects": None},
            "editor": {"username": "editor", "role": "editor", "projects": ["p1"]},
            "finEditor": {"username": "finEditor", "role": "editor", "projects": ["p1"],
                          "financeEdit": True},
            "reader": {"username": "reader", "role": "viewer", "projects": ["p1"],
                       "financeView": True},
            "outsider": {"username": "outsider", "role": "editor", "projects": ["p2"],
                         "financeEdit": True},
        }
        self.i = 0

    def run_command(self, type_name, *, actor="admin", event_id=None, at=NOW, **kwargs):
        self.i += 1
        command = {"type": type_name, "eventId": event_id or f"evt{self.i}", **kwargs}
        result = apply_finance_command(self.state, command, actor=actor, accounts=self.accounts,
                                       cards=self.cards, projects=self.projects, now=at)
        self.state = result["state"]
        return result

    def sale(self, **changes):
        basic = {"customer": {"name": "Mina Co", "reference": "CUST-1"},
                 "lines": [{"id": "a", "description": "Design", "quantity": 2, "unitPrice": 3000},
                           {"id": "b", "description": "Print", "quantity": 1, "unitPrice": 1000}],
                 "discount": 300, "tax": 500, "advance": 1000, "autoInvoice": True}
        return {**basic, **changes}

    def configure_and_complete(self):
        self.run_command("contract.set", cardId="c1", sale=self.sale())
        self.cards[0]["status"] = "done"
        return self.run_command("completion.record", actor="editor", cardId="c1", completionId="complete-v1")

    def invoice(self):
        self.assertTrue(self.state["invoices"])
        return self.state["invoices"][-1]

    def test_empty_state_is_valid_and_serializable(self):
        self.assertTrue(validate_finance_state(self.state))
        self.assertEqual(json.loads(json.dumps(self.state)), self.state)

    def test_money_integer_and_decimal_are_exact_and_reject_floats(self):
        self.assertEqual(amount("000" if False else "0"), 0)
        self.assertEqual(amount("123.00"), 123)
        self.assertEqual(amount(10**15), 10**15)
        for bad in (True, False, 0.0, 2.0, float("nan"), float("inf"),
                    -1, "-1", "1.01", "1.5", "1e4", "1,000", "+1", "01", " 1 ",
                    "0.1", None, {}, 10**15 + 1, "9999999999999999"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                amount(bad)

    def test_cost_inherits_project_and_disabled_data_is_retained(self):
        summary = card_cost_summary(self.cards[0], self.projects[0])
        self.assertEqual(summary["estimatedTotal"], 800)
        self.assertEqual(summary["includedEstimated"], 800)
        self.assertEqual(summary["actualTotal"], 0)
        self.run_command("cost.toggle", cardId="c1", costEnabled=False)
        disabled = card_cost_summary(self.cards[0], self.projects[0],
                                     override=self.state["cardCosts"]["c1"])
        self.assertFalse(disabled["enabled"])
        self.assertEqual(disabled["estimatedTotal"], 800)
        self.assertEqual(disabled["includedEstimated"], 0)
        self.run_command("cost.toggle", cardId="c1", costEnabled=None)
        self.assertTrue(card_cost_summary(self.cards[0], self.projects[0],
                                         override=self.state["cardCosts"]["c1"])["enabled"])

    def test_explicit_opt_in_overrides_project_off(self):
        summary = card_cost_summary(self.cards[1], self.projects[1])
        self.assertEqual(summary["includedEstimated"], 0)
        self.run_command("cost.toggle", cardId="c2", costEnabled=True)
        new = card_cost_summary(self.cards[1], self.projects[1],
                                override=self.state["cardCosts"]["c2"])
        self.assertEqual(new["includedEstimated"], 490)
        self.assertEqual(new["estimatedTotal"], 490)

    def test_named_checklist_migration_is_not_double_counted(self):
        self.cards[0]["checklists"] = [{"id": "checklist-legacy", "items": deepcopy(self.cards[0]["checklist"])}]
        self.assertEqual(card_cost_summary(self.cards[0], self.projects[0])["estimatedTotal"], 800)
        self.cards[0]["checklists"].append({"id": "custom", "items": [{"id": "f", "cost": 10}]})
        self.assertEqual(card_cost_summary(self.cards[0], self.projects[0])["estimatedTotal"], 810)

    def test_removed_checklist_does_not_erase_recorded_actual_cost(self):
        self.run_command("cost.set", cardId="c1", value={
            "cardId": "c1", "costEnabled": True, "estimatedDirect": 500, "actualDirect": 450,
            "items": [{"id": "checklist-legacy:x", "estimated": 100, "actual": 95}]})
        self.cards[0]["checklist"] = [self.cards[0]["checklist"][1]]
        summary = card_cost_summary(self.cards[0], self.projects[0],
                                    override=self.state["cardCosts"]["c1"])
        self.assertEqual(summary["estimatedTotal"], 800)
        self.assertEqual(summary["actualTotal"], 545)
        self.assertTrue(next(item for item in summary["checklist"] if item["id"].endswith(":x"))["orphaned"])
        self.run_command("cost.toggle", cardId="c1", costEnabled=False)
        self.assertEqual(self.state["cardCosts"]["c1"]["items"][0]["actual"], 95)

    def test_edit_costs_separately_actual_and_estimated(self):
        config = {"cardId": "c1", "costEnabled": True,
                  "estimatedDirect": "1200.00", "actualDirect": "900.00",
                  "items": [{"id": "checklist-legacy:x", "estimated": "500", "actual": 600},
                            {"id": "checklist-legacy:y", "estimated": 400, "actual": "800"}]}
        result = self.run_command("cost.set", cardId="c1", value=config, actor="finEditor")
        self.assertEqual(result["result"]["estimatedTotal"], 2100)
        self.assertEqual(result["result"]["actualTotal"], 2300)
        self.assertEqual(self.state["cardCosts"]["c1"]["estimatedDirect"], 1200)
        self.assertEqual(project_cost_summary(self.state, "p1", actor="finEditor",
                                             accounts=self.accounts, cards=self.cards,
                                             projects=self.projects)["actualTotal"], 2300)
        self.assertEqual(self.state["ledger"][-1]["action"], "cost.set")

    def test_cost_edit_rejects_out_of_scope_and_unknown_checklist(self):
        config = {"cardId": "c1", "costEnabled": None, "estimatedDirect": 10,
                  "actualDirect": 5, "items": [{"id": "not-real", "estimated": 3, "actual": 0}]}
        for actor in ("editor", "reader", "outsider"):
            with self.subTest(actor=actor), self.assertRaises(PermissionError):
                self.run_command("cost.set", cardId="c1", value=config, actor=actor)
        with self.assertRaises(ValueError):
            self.run_command("cost.set", cardId="c1", value=config)

    def test_sale_is_explicit_never_from_internal_cost_or_project_price(self):
        self.configure_and_complete()
        invoice = self.invoice()
        self.assertEqual(invoice["sale"]["subtotal"], 7000)
        self.assertEqual(invoice["sale"]["total"], 7200)
        self.assertEqual(invoice["sale"]["due"], 6200)
        self.assertNotEqual(invoice["sale"]["total"], self.projects[0]["price"])
        self.assertNotEqual(invoice["sale"]["total"], 800)
        self.assertEqual(invoice_status(self.state, invoice["id"])["status"], "Draft")
        self.assertIsNone(invoice_status(self.state, invoice["id"])["number"])

    def test_only_explicit_contract_auto_invoice_creates_draft(self):
        self.cards[0]["status"] = "done"
        result = self.run_command("completion.record", cardId="c1", completionId="without-contract")
        self.assertFalse(result["result"]["invoiceCreated"])
        self.run_command("contract.set", cardId="c1", sale=self.sale(autoInvoice=False))
        result = self.run_command("completion.record", cardId="c1", completionId="disabled")
        self.assertFalse(result["result"]["invoiceCreated"])
        self.assertEqual(self.state["invoices"], [])

    def test_completion_requires_completed_card(self):
        self.run_command("contract.set", cardId="c1", sale=self.sale())
        with self.assertRaises(ValueError):
            self.run_command("completion.record", cardId="c1", completionId="not-complete")
        self.assertFalse(self.state["invoices"])

    def test_repeated_completion_and_retry_never_double_invoices(self):
        self.configure_and_complete()
        first = self.invoice()["id"]
        same = self.run_command("completion.record", actor="editor", cardId="c1", completionId="complete-v1")
        self.assertFalse(same["result"]["invoiceCreated"])
        changed = self.run_command("completion.record", actor="editor", cardId="c1", completionId="complete-v2")
        self.assertFalse(changed["result"]["invoiceCreated"])
        self.assertEqual(len(self.state["invoices"]), 1)
        self.assertEqual(self.invoice()["id"], first)
        self.assertEqual(self.state["completionIds"]["complete-v2"]["invoiceId"], first)

    def test_invoice_snapshots_immutable_even_when_contract_changes(self):
        self.configure_and_complete()
        initial = deepcopy(self.invoice())
        self.run_command("contract.set", cardId="c1", sale=self.sale(lines=[
            {"id": "new", "description": "New price", "quantity": 1, "unitPrice": 9000}]))
        self.assertEqual(initial, self.invoice())
        self.assertEqual(self.invoice()["sale"]["total"], 7200)
        self.run_command("completion.record", cardId="c1", completionId="second-after-amendment")
        self.assertEqual(len(self.state["invoices"]), 2)  # deliberate new contract version

    def test_admin_issue_review_payments_and_sequential_numbers(self):
        self.configure_and_complete()
        first_id = self.invoice()["id"]
        with self.assertRaises(ValueError):
            self.run_command("invoice.issue", invoiceId=first_id)
        self.run_command("invoice.review", invoiceId=first_id)
        issued = self.run_command("invoice.issue", invoiceId=first_id)
        self.assertEqual(issued["result"]["number"], 1)
        self.assertEqual(self.state["nextInvoiceNumber"], 2)
        self.assertEqual(invoice_status(self.state, first_id)["status"], "Issued")
        self.run_command("invoice.payment", invoiceId=first_id, amount="1200")
        self.assertEqual(invoice_status(self.state, first_id)["remaining"], 5000)
        self.run_command("invoice.payment", invoiceId=first_id, amount=5000)
        self.assertEqual(invoice_status(self.state, first_id)["status"], "Paid")
        self.assertEqual(invoice_status(self.state, first_id)["remaining"], 0)
        self.assertEqual(self.state["invoices"][0]["sale"]["due"], 6200)

    def test_payment_cannot_be_duplicated_or_overpaid(self):
        self.configure_and_complete()
        identifier = self.invoice()["id"]
        self.run_command("invoice.review", invoiceId=identifier)
        self.run_command("invoice.issue", invoiceId=identifier)
        with self.assertRaises(ValueError):
            self.run_command("invoice.payment", invoiceId=identifier, amount=0)
        with self.assertRaises(ValueError):
            self.run_command("invoice.payment", invoiceId=identifier, amount=6201)
        self.run_command("invoice.payment", invoiceId=identifier, amount=6200)
        with self.assertRaises(ValueError):
            self.run_command("invoice.payment", invoiceId=identifier, amount=1)

    def test_corrections_append_new_invoice_and_retire_original(self):
        self.configure_and_complete()
        original = deepcopy(self.invoice())
        result = self.run_command("invoice.revise", invoiceId=original["id"],
                                  sale=self.sale(discount=500), reason="Client approved revision")
        revision_id = result["result"]["invoiceId"]
        self.assertNotEqual(revision_id, original["id"])
        self.assertEqual(self.state["invoices"][0], original)
        self.assertEqual(self.invoice()["supersedesId"], original["id"])
        self.assertEqual(invoice_status(self.state, original["id"])["status"], "Superseded")
        self.assertEqual(invoice_status(self.state, revision_id)["status"], "Draft")
        with self.assertRaises(ValueError):
            self.run_command("invoice.review", invoiceId=original["id"])

    def test_issued_and_paid_invoice_cannot_be_revised(self):
        self.configure_and_complete()
        identifier = self.invoice()["id"]
        self.run_command("invoice.review", invoiceId=identifier)
        self.run_command("invoice.issue", invoiceId=identifier)
        with self.assertRaises(ValueError):
            self.run_command("invoice.revise", invoiceId=identifier, sale=self.sale(), reason="late")

    def test_cancellation_is_audit_event_no_mutation_or_reissue(self):
        self.configure_and_complete()
        before = deepcopy(self.invoice())
        self.run_command("invoice.review", invoiceId=before["id"])
        self.run_command("invoice.issue", invoiceId=before["id"])
        self.run_command("invoice.cancel", invoiceId=before["id"], reason="Duplicate order")
        self.assertEqual(invoice_status(self.state, before["id"])["status"], "Cancelled")
        self.assertEqual(self.state["invoices"][0], before)
        self.assertEqual(self.state["nextInvoiceNumber"], 2)
        with self.assertRaises(ValueError):
            self.run_command("invoice.issue", invoiceId=before["id"])
        with self.assertRaises(ValueError):
            self.run_command("invoice.cancel", invoiceId=before["id"], reason="again")

    def test_cannot_cancel_partially_or_fully_paid(self):
        self.configure_and_complete()
        identifier = self.invoice()["id"]
        self.run_command("invoice.review", invoiceId=identifier)
        self.run_command("invoice.issue", invoiceId=identifier)
        self.run_command("invoice.payment", invoiceId=identifier, amount=100)
        with self.assertRaises(ValueError):
            self.run_command("invoice.cancel", invoiceId=identifier, reason="Unsafe refund")

    def test_sale_validation_no_invented_tax_or_fractional_money(self):
        for sale in [
            self.sale(lines=[]),
            self.sale(lines=[{"id": "x", "description": "A", "quantity": 0, "unitPrice": 100}]),
            self.sale(lines=[{"id": "x", "description": "A", "quantity": True, "unitPrice": 100}]),
            self.sale(tax="0.5"),
            self.sale(discount=7001),
            self.sale(advance=7201),
            self.sale(lines=[{"id": "x", "description": "Large", "quantity": 100000,
                              "unitPrice": 10**15}]),
            self.sale(customer={"name": "", "reference": ""}),
            self.sale(autoInvoice="true"),
        ]:
            with self.subTest(sale=sale), self.assertRaises(ValueError):
                self.run_command("contract.set", cardId="c1", sale=sale)
        self.assertEqual(self.state["contracts"], [])

    def test_role_and_project_scope_enforced_in_reads_and_commands(self):
        for actor in ("editor", "finEditor", "reader", "outsider"):
            with self.subTest(actor=actor), self.assertRaises(PermissionError):
                self.run_command("contract.set", cardId="c1", sale=self.sale(), actor=actor)
        self.configure_and_complete()
        identifier = self.invoice()["id"]
        for actor in ("editor", "finEditor", "reader", "outsider"):
            with self.subTest(actor=actor), self.assertRaises(PermissionError):
                self.run_command("invoice.review", invoiceId=identifier, actor=actor)
        def invoices(actor):
            return list_invoices(self.state, actor=actor, accounts=self.accounts,
                                 cards=self.cards, projects=self.projects)
        self.assertEqual(len(invoices("reader")), 1)
        self.assertEqual(len(invoices("finEditor")), 1)
        self.assertFalse(invoices("editor"))
        self.assertFalse(invoices("outsider"))
        with self.assertRaises(PermissionError):
            list_invoices(self.state, actor="outsider", accounts=self.accounts,
                          cards=self.cards, projects=self.projects, project_id="p1")
        self.assertEqual(len(list_finance_ledger(self.state, actor="reader",
                                                accounts=self.accounts, cards=self.cards,
                                                projects=self.projects)), 3)

    def test_completion_record_can_be_submitted_by_editor_without_finance_access(self):
        self.run_command("contract.set", cardId="c1", sale=self.sale())
        self.cards[0]["status"] = "done"
        response = self.run_command("completion.record", cardId="c1", actor="editor", completionId="card-done")
        self.assertEqual(response["result"], {"invoiceCreated": True, "duplicateCompletion": False})
        self.assertNotIn("total", response["result"])
        with self.assertRaises(PermissionError):
            self.run_command("completion.record", cardId="c2", actor="editor", completionId="other")

    def test_event_retries_survive_json_roundtrip_and_recheck_role(self):
        cmd = {"type": "cost.toggle", "eventId": "retry-t1", "cardId": "c1", "costEnabled": True}
        baseline = deepcopy(self.state)
        first = apply_finance_command(self.state, cmd, actor="finEditor", accounts=self.accounts,
                                      cards=self.cards, projects=self.projects, now=NOW)
        self.assertEqual(self.state, baseline)
        restored = json.loads(json.dumps(first["state"]))
        twice = apply_finance_command(restored, cmd, actor="finEditor", accounts=self.accounts,
                                      cards=self.cards, projects=self.projects, now=LATER)
        self.assertFalse(twice["changed"])
        self.assertEqual(restored, twice["state"])
        with self.assertRaisesRegex(ValueError, "Idempotency key reused"):
            apply_finance_command(restored, {**cmd, "costEnabled": False}, actor="finEditor",
                                  accounts=self.accounts, cards=self.cards, projects=self.projects, now=LATER)
        self.accounts["finEditor"]["financeEdit"] = False
        with self.assertRaises(PermissionError):
            apply_finance_command(restored, cmd, actor="finEditor", accounts=self.accounts,
                                  cards=self.cards, projects=self.projects, now=LATER)

    def test_completion_id_cannot_rebind_to_other_card(self):
        self.cards[0]["status"] = "done"
        self.run_command("completion.record", cardId="c1", completionId="unique-completion")
        with self.assertRaises(ValueError):
            self.run_command("completion.record", cardId="c2", completionId="unique-completion")

    def test_invoice_issue_retry_does_not_increment_sequence(self):
        self.configure_and_complete()
        identifier = self.invoice()["id"]
        self.run_command("invoice.review", invoiceId=identifier)
        first = self.run_command("invoice.issue", invoiceId=identifier, event_id="issue-once")
        second = self.run_command("invoice.issue", invoiceId=identifier, event_id="issue-once", at=LATER)
        self.assertFalse(second["changed"])
        self.assertEqual(first["result"]["number"], second["result"]["number"])
        self.assertEqual(self.state["nextInvoiceNumber"], 2)

    def test_hash_tampering_detected_in_invoices_and_audit(self):
        self.configure_and_complete()
        changed_invoice = deepcopy(self.state)
        changed_invoice["invoices"][0]["sale"]["total"] = 1
        with self.assertRaises(ValueError):
            validate_finance_state(changed_invoice)
        changed_ledger = deepcopy(self.state)
        changed_ledger["ledger"][0]["actor"] = "attacker"
        with self.assertRaisesRegex(ValueError, "Ledger hash chain"):
            validate_finance_state(changed_ledger)
        missing_field = deepcopy(self.state)
        missing_field["invoices"][0]["sale"].pop("tax")
        with self.assertRaises(ValueError):
            validate_finance_state(missing_field)
        bad_sequence = deepcopy(self.state)
        bad_sequence["nextInvoiceNumber"] = 2
        with self.assertRaisesRegex(ValueError, "number sequence"):
            validate_finance_state(bad_sequence)

    def test_unsupported_input_and_bad_times_are_rejected(self):
        cmd = {"type": "contract.set", "eventId": "e1", "cardId": "c1",
               "sale": self.sale(), "unexpected": "foo"}
        with self.assertRaises(ValueError):
            apply_finance_command(self.state, cmd, actor="admin", accounts=self.accounts,
                                  cards=self.cards, projects=self.projects, now=NOW)
        with self.assertRaises(ValueError):
            self.run_command("contract.set", cardId="c1", sale=self.sale(), at="2026-10-20T16:00:00")
        self.assertEqual(self.state, empty_finance_state())

    def test_invoice_and_ledger_reads_are_detached(self):
        self.configure_and_complete()
        snapshots = list_invoices(self.state, actor="admin", accounts=self.accounts,
                                  cards=self.cards, projects=self.projects)
        snapshots[0]["sale"]["total"] = 1
        log = list_finance_ledger(self.state, actor="admin", accounts=self.accounts,
                                  cards=self.cards, projects=self.projects)
        log[0]["actor"] = "attacker"
        self.assertEqual(self.invoice()["sale"]["total"], 7200)
        self.assertEqual(self.state["ledger"][0]["actor"], "admin")


if __name__ == "__main__":
    unittest.main()
