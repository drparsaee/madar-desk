"""Synthetic-only behavioral and hostile inventory domain tests."""
from dataclasses import replace
import unittest

from ir_inventory_rial import (
    BusinessSource, InventoryAccountMapping, InventoryConflict, InventoryError,
    ItemSpec, StockAuthority, StockEvent, append_stock_event, new_inventory_state,
    propose_inventory_journal, replay_inventory, to_base_quantity,
)


class InventoryDomainTests(unittest.TestCase):
    def setUp(self):
        self.item = ItemSpec("co1", "item1", "kg", 1000)
        self.state = new_inventory_state("co1", (self.item,), ("a", "b"))
        self.accounts = InventoryAccountMapping(
            "co1", "112", "219", "511", "719", "819", "218")

    def event(self, kind, event_id, qty, *, source_id=None, **kwargs):
        base = {"event_id": event_id, "company_id": "co1",
                "actor_id": "worker", "kind": kind,
                "source": BusinessSource(kind.lower(), source_id or ("document-" + event_id)),
                "warehouse_id": "a", "item_id": "item1",
                "unit": "kg", "base_units_per_unit": 1000,
                "quantity_base": qty}
        base.update(kwargs)
        return StockEvent(**base)

    def authority(self, event, **kwargs):
        base = {"company_id": "co1", "actor_ids": frozenset({"worker"}),
                "warehouse_ids": frozenset({"a", "b"}),
                "item_ids": frozenset({"item1"}),
                "source_scopes": frozenset({(event.source.kind, event.source.source_id)})}
        base.update(kwargs)
        return StockAuthority(**base)

    def append(self, event, state=None, auth=None):
        prior = state if state is not None else self.state
        return append_stock_event(prior, event, auth or self.authority(event),
                                  expected_revision=prior.revision)

    def position(self, state, warehouse="a"):
        positions = replay_inventory(state).positions
        return next((p for p in positions if p.warehouse_id == warehouse), None)

    def test_explicit_exact_measurement_and_non_float(self):
        self.assertEqual(to_base_quantity(self.item, "1.025"), 1025)
        self.assertEqual(to_base_quantity(self.item, "0.000"), 0)
        for invalid in ("0.0001", "1e3", "-1", "1,000", "1.2kg", "01", " 1", "1."):
            with self.subTest(invalid=invalid), self.assertRaises(InventoryError):
                to_base_quantity(self.item, invalid)
        with self.assertRaises(InventoryError):
            self.event("RECEIPT", "bad", True, cost_rial=1)
        with self.assertRaises(InventoryError):
            self.event("RECEIPT", "bad", 1, cost_rial=2.4)
        with self.assertRaises(InventoryError):
            self.event("RECEIPT", "bad", 1, cost_rial=9_007_199_254_740_992)

    def test_fifo_fractional_rial_is_exact_over_full_lot(self):
        state = self.append(self.event("RECEIPT", "r", 3, cost_rial=10))
        state = self.append(self.event("ISSUE", "i1", 1), state)
        self.assertEqual(state.events[-1].effects.valued_cost_rial, 3)
        self.assertEqual((self.position(state).valued_quantity_base,
                          self.position(state).value_rial), (2, 7))
        state = self.append(self.event("ISSUE", "i2", 2), state)
        self.assertEqual(state.events[-1].effects.valued_cost_rial, 7)
        self.assertIsNone(self.position(state))
        self.assertEqual(replay_inventory(state).event_count, 3)

    def test_fifo_across_separate_receipts_and_atomic_failure(self):
        state = self.append(self.event("RECEIPT", "r1", 2, cost_rial=12))
        state = self.append(self.event("RECEIPT", "r2", 2, cost_rial=18), state)
        next_state = self.append(self.event("ISSUE", "i", 3), state)
        self.assertEqual(next_state.events[-1].effects.valued_cost_rial, 21)
        self.assertEqual(self.position(next_state).value_rial, 9)
        with self.assertRaises(InventoryError):
            self.append(self.event("ISSUE", "overdraw", 2), next_state)
        self.assertEqual(len(next_state.events), 3)

    def test_costless_receipt_stages_until_explicit_pricing(self):
        state = self.append(self.event("RECEIPT", "r", 3))
        self.assertEqual(self.position(state).staged_quantity_base, 3)
        self.assertEqual(self.position(state).valued_quantity_base, 0)
        self.assertEqual(self.position(state).value_rial, 0)
        self.assertIsNone(propose_inventory_journal(state, "r", self.accounts))
        with self.assertRaises(InventoryError):
            self.append(self.event("ISSUE", "i", 1), state)
        state = self.append(self.event("PRICE", "price", 3,
                             related_event_id="r", cost_rial=10), state)
        self.assertEqual((self.position(state).valued_quantity_base,
                          self.position(state).staged_quantity_base,
                          self.position(state).value_rial), (3, 0, 10))
        self.assertEqual(self.debits(state, "price"), 10)
        with self.assertRaises(InventoryError):
            self.append(self.event("PRICE", "second", 3,
                        related_event_id="r", cost_rial=10), state)

    def debits(self, state, event_id):
        proposal = propose_inventory_journal(state, event_id, self.accounts)
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal.company_id, "co1")
        self.assertEqual(sum(line.debit_rial for line in proposal.lines),
                         sum(line.credit_rial for line in proposal.lines))
        return sum(line.debit_rial for line in proposal.lines)

    def test_transfer_preserves_fifo_cost_and_warehouse_isolation(self):
        state = self.append(self.event("RECEIPT", "r", 4, cost_rial=10))
        state = self.append(self.event("TRANSFER", "x", 2,
                             destination_warehouse_id="b"), state)
        self.assertEqual((self.position(state).value_rial,
                          self.position(state, "b").value_rial), (5, 5))
        self.assertIsNone(propose_inventory_journal(state, "x", self.accounts))
        state = self.append(self.event("ISSUE", "i", 1, warehouse_id="b"), state)
        self.assertEqual(state.events[-1].effects.valued_cost_rial, 2)
        self.assertEqual(self.position(state, "b").value_rial, 3)
        self.assertEqual(self.debits(state, "i"), 2)

    def test_exact_return_reverses_issue_once_with_provenance(self):
        state = self.append(self.event("RECEIPT", "r", 3, cost_rial=10))
        state = self.append(self.event("ISSUE", "i", 2), state)
        self.assertEqual(self.position(state).value_rial, 4)
        state = self.append(self.event("RETURN", "ret", 2,
                             related_event_id="i", reason="Customer returned goods"), state)
        self.assertEqual(self.position(state).value_rial, 10)
        self.assertEqual(self.position(state).valued_quantity_base, 3)
        self.assertEqual(self.debits(state, "ret"), 6)
        with self.assertRaises(InventoryConflict):
            self.append(self.event("REVERSAL", "rev", 2, related_event_id="i",
                                   reason="Duplicate reverse"), state)
        with self.assertRaises(InventoryError):
            self.event("RETURN", "partial", 1, related_event_id="i", reason="")

    def test_issue_reversal_exact_inverse_and_no_reversal_of_reversal(self):
        state = self.append(self.event("RECEIPT", "r", 3, cost_rial=10))
        state = self.append(self.event("ISSUE", "i", 1), state)
        state = self.append(self.event("REVERSAL", "rev", 1,
                         related_event_id="i", reason="Voided outgoing ticket"), state)
        self.assertEqual(self.position(state).value_rial, 10)
        self.assertEqual(self.debits(state, "rev"), 3)
        with self.assertRaises(InventoryError):
            self.append(self.event("REVERSAL", "rev2", 1,
                        related_event_id="rev", reason="Nested reversal"), state)

    def test_receipt_reversal_requires_unconsumed_specific_lot(self):
        state = self.append(self.event("RECEIPT", "r", 3, cost_rial=10))
        state = self.append(self.event("ISSUE", "i", 1), state)
        with self.assertRaises(InventoryError):
            self.append(self.event("REVERSAL", "rev", 3,
                        related_event_id="r", reason="Voided purchase"), state)
        state = self.append(self.event("RECEIPT", "r2", 2, cost_rial=8), state)
        state = self.append(self.event("REVERSAL", "rev2", 2,
                         related_event_id="r2", reason="Voided second purchase"), state)
        self.assertEqual(self.position(state).value_rial, 7)
        self.assertEqual(self.debits(state, "rev2"), 8)

    def test_transfer_reversal_denied_if_transferred_lot_consumed(self):
        state = self.append(self.event("RECEIPT", "r", 3, cost_rial=10))
        state = self.append(self.event("TRANSFER", "x", 2,
                        destination_warehouse_id="b"), state)
        rev_event = self.event("REVERSAL", "r-x", 2,
                               related_event_id="x", reason="Wrong warehouse")
        with self.assertRaises(InventoryError):
            self.append(rev_event, state, self.authority(
                rev_event, warehouse_ids=frozenset({"a"})))
        reversible = self.append(rev_event, state)
        self.assertIsNone(self.position(reversible, "b"))
        self.assertEqual(self.position(reversible).value_rial, 10)
        state = self.append(self.event("ISSUE", "i", 1, warehouse_id="b"), state)
        with self.assertRaises(InventoryError):
            self.append(self.event("REVERSAL", "r-x", 2,
                        related_event_id="x", reason="Wrong warehouse"), state)

    def test_price_reversal_restages_and_supports_corrected_pricing(self):
        state = self.append(self.event("RECEIPT", "r", 2))
        state = self.append(self.event("PRICE", "p", 2, related_event_id="r",
                                      cost_rial=11), state)
        state = self.append(self.event("REVERSAL", "rvp", 2,
                                      related_event_id="p", reason="Cost correction"), state)
        self.assertEqual(self.position(state).staged_quantity_base, 2)
        self.assertEqual(self.position(state).value_rial, 0)
        state = self.append(self.event("PRICE", "p2", 2,
                            related_event_id="r", cost_rial=12), state)
        self.assertEqual(self.position(state).value_rial, 12)

    def test_cycle_count_audit_positive_negative_and_stale_baseline(self):
        state = self.append(self.event("RECEIPT", "r", 4, cost_rial=20))
        grow = self.event("ADJUSTMENT", "count1", 2, expected_quantity_base=4,
                          counted_quantity_base=6, cost_rial=11,
                          reason="Physical count: two extra kilograms")
        state = self.append(grow, state)
        self.assertEqual(self.position(state).value_rial, 31)
        self.assertEqual(self.debits(state, "count1"), 11)
        shrink = self.event("ADJUSTMENT", "count2", 3, expected_quantity_base=6,
                            counted_quantity_base=3, reason="Damaged goods")
        state = self.append(shrink, state)
        self.assertEqual(self.position(state).value_rial, 16)
        self.assertEqual(self.debits(state, "count2"), 15)
        with self.assertRaises(InventoryConflict):
            self.append(self.event("ADJUSTMENT", "stale", 1,
                        expected_quantity_base=6, counted_quantity_base=7,
                        cost_rial=1, reason="Forged count"), state)
        with self.assertRaises(InventoryError):
            self.event("ADJUSTMENT", "bad", 1,
                       expected_quantity_base=2, counted_quantity_base=3,
                       reason="No price")

    def test_cycle_count_rejects_unpriced_stock(self):
        state = self.append(self.event("RECEIPT", "r", 5))
        with self.assertRaises(InventoryError):
            self.append(self.event("ADJUSTMENT", "count", 5,
                        expected_quantity_base=0, counted_quantity_base=5,
                        cost_rial=25, reason="Cannot mix staged stock"), state)

    def test_replayed_event_id_same_payload_idempotent(self):
        event = self.event("RECEIPT", "r", 3, cost_rial=10)
        auth = self.authority(event)
        once = self.append(event, auth=auth)
        twice = append_stock_event(once, event, auth, expected_revision=self.state.revision)
        self.assertIs(once, twice)
        self.assertEqual(len(twice.events), 1)

    def test_source_uniqueness_across_distinct_event_ids(self):
        state = self.append(self.event("RECEIPT", "r", 3, cost_rial=10,
                                       source_id="purchase1"))
        with self.assertRaises(InventoryConflict):
            self.append(self.event("RECEIPT", "r2", 4, cost_rial=11,
                        source_id="purchase1"), state)
        with self.assertRaises(InventoryConflict):
            self.append(self.event("RECEIPT", "r", 9, cost_rial=10,
                        source_id="purchase1"), state)
        with self.assertRaises(InventoryConflict):
            self.append(self.event("ISSUE", "i", 1,
                        source_id="purchase1"), state)

    def test_different_company_source_namespace_is_separate(self):
        event = self.event("RECEIPT", "r", 1, cost_rial=10,
                           source_id="purchase1")
        state = self.append(event)
        other_item = ItemSpec("co2", "item1", "kg", 1000)
        other = new_inventory_state("co2", (other_item,), ("a",))
        other_event = replace(event, company_id="co2")
        auth = StockAuthority("co2", frozenset({"worker"}),
                              frozenset({"a"}), frozenset({"item1"}),
                              frozenset({("receipt", "purchase1")}))
        other = append_stock_event(other, other_event, auth,
                                   expected_revision=other.revision)
        self.assertEqual(self.position(state).value_rial, 10)
        self.assertEqual(replay_inventory(other).positions[0].value_rial, 10)
        self.assertNotEqual(state.revision, other.revision)

    def test_fifo_slice_budgets_fail_closed(self):
        # Transfers would have two slices per consumed lot; 129 lots exceed 256.
        state = self.state
        for index in range(129):
            state = self.append(self.event("RECEIPT", "r" + str(index),
                                         1, cost_rial=1), state)
        with self.assertRaises(InventoryError):
            self.append(self.event("TRANSFER", "many", 129,
                                   destination_warehouse_id="b"), state)
        self.assertEqual(self.position(state).valued_quantity_base, 129)
        self.assertIsNone(self.position(state, "b"))

    def test_cycle_variance_reversal_proposals_restore_original_accounts(self):
        state = self.append(self.event("RECEIPT", "r", 5, cost_rial=25))
        state = self.append(self.event("ADJUSTMENT", "low", 2,
                            expected_quantity_base=5, counted_quantity_base=3,
                            reason="Stock breakage"), state)
        self.assertEqual(self.debits(state, "low"), 10)
        state = self.append(self.event("REVERSAL", "recount", 2,
                            related_event_id="low", reason="Wrong physical count"), state)
        p = propose_inventory_journal(state, "recount", self.accounts)
        self.assertEqual([(line.account_code, line.debit_rial, line.credit_rial)
                          for line in p.lines], [("112", 10, 0), ("819", 0, 10)])

    def test_old_revision_rejected(self):
        event = self.event("RECEIPT", "r", 1, cost_rial=10)
        state = self.append(event)
        with self.assertRaises(InventoryConflict):
            append_stock_event(state, self.event("ISSUE", "i", 1),
                               self.authority(self.event("ISSUE", "i", 1)),
                               expected_revision=self.state.revision)

    def test_cross_company_actor_warehouse_item_source_and_work_rejected(self):
        event = self.event("RECEIPT", "r", 1, cost_rial=10)
        self.assertRaises(InventoryError, self.append, event,
                          auth=self.authority(event, company_id="foreign"))
        self.assertRaises(InventoryError, self.append, event,
                          auth=self.authority(event, actor_ids=frozenset({"intruder"})))
        self.assertRaises(InventoryError, self.append, event,
                          auth=self.authority(event, source_scopes=frozenset()))
        self.assertRaises(InventoryError, self.append, event,
                          auth=self.authority(event, warehouse_ids=frozenset({"b"})))
        self.assertRaises(InventoryError, self.append, event,
                          auth=self.authority(event, item_ids=frozenset()))
        foreign = replace(event, company_id="other")
        self.assertRaises(InventoryError, self.append, foreign)
        wrong_unit = replace(event, base_units_per_unit=1)
        self.assertRaises(InventoryError, self.append, wrong_unit)
        work = replace(event, project_id="p", job_id="j", cost_center_id="cc")
        self.assertRaises(InventoryError, self.append, work)
        auth = self.authority(work, project_ids=frozenset({"p"}),
                              work_scopes=frozenset({("p", "j", "cc")}))
        self.assertEqual(len(self.append(work, auth=auth).events), 1)

    def test_forged_effects_hash_or_history_reordering_detected(self):
        state = self.append(self.event("RECEIPT", "r", 3, cost_rial=10))
        state = self.append(self.event("ISSUE", "i", 1), state)
        first, second = state.events
        with self.assertRaises(InventoryError):
            replay_inventory(replace(state, events=(
                replace(first, effects=replace(first.effects, asset_delta_rial=9)),
                second)))
        with self.assertRaises(InventoryError):
            replay_inventory(replace(state, events=(second, first)))
        with self.assertRaises(InventoryError):
            replay_inventory(replace(state, events=(
                first, replace(second, previous_hash="0" * 64))))
        with self.assertRaises(InventoryError):
            replay_inventory(replace(state, events=(
                first, replace(second, event=replace(second.event, quantity_base=2)))))

    def test_catalog_is_company_locked_bounded_and_deterministic(self):
        with self.assertRaises(InventoryError):
            new_inventory_state("co1", (ItemSpec("foreign", "item1", "kg", 1000),), ("a",))
        with self.assertRaises(InventoryError):
            new_inventory_state("co1", (self.item, self.item), ("a",))
        with self.assertRaises(InventoryError):
            new_inventory_state("co1", (self.item,), ("a", "a"))
        with self.assertRaises(InventoryError):
            self.event("RECEIPT", "oversize", 1_000_000_000_001, cost_rial=1)
        self.assertEqual(self.state.revision,
                         new_inventory_state("co1", (self.item,), ("b", "a")).revision)

    def test_gl_proposals_are_balanced_and_refuse_wrong_company(self):
        state = self.append(self.event("RECEIPT", "r", 4, cost_rial=16))
        state = self.append(self.event("ISSUE", "i", 1), state)
        self.assertEqual(self.debits(state, "r"), 16)
        self.assertEqual(self.debits(state, "i"), 4)
        p = propose_inventory_journal(state, "i", self.accounts)
        self.assertEqual((p.lines[0].account_code, p.lines[1].account_code),
                         ("511", "112"))
        with self.assertRaises(InventoryError):
            propose_inventory_journal(state, "i",
                replace(self.accounts, company_id="foreign"))
        with self.assertRaises(InventoryError):
            propose_inventory_journal(state, "missing", self.accounts)


if __name__ == "__main__":
    unittest.main()
