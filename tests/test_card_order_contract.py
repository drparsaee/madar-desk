"""Host contract for optional task.cardOrder, matching src/cardorder.js.

Only disposable local data is used. This suite intentionally exposes missing
host validation as a genuine failure until the implementation is integrated.
"""

from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from data_model import normalize_plus, validate_plus
import native_app


MAX_CARD_ORDER = 1_000_000  # Contract in src/cardorder.js.


def original_state():
    """A fresh synthetic v1 state with explicit nonzero financial metadata."""
    state = native_app.initial_state()
    state["projects"][1].update(price=8_800_001, costEnabled=True)
    card = state["tasks"][0]
    card.update(cost=3_700_005, costEnabled=True, costCategory="چاپ", costDate="2026-10-21")
    card["checklist"][0].update(cost=88_111, costCategory="برش", costDate="2026-10-20")
    return state


def finance_snapshot(state):
    return {
        "projects": [{"id": p["id"], "price": p.get("price"),
                      "costEnabled": p.get("costEnabled")} for p in state["projects"]],
        "cards": [{"id": c["id"], "cost": c.get("cost"),
                   "costEnabled": c.get("costEnabled"),
                   "costCategory": c.get("costCategory"),
                   "costDate": c.get("costDate"),
                   "checklist": deepcopy(c["checklist"])} for c in state["tasks"]],
    }


class CardOrderPureContractTests(unittest.TestCase):
    def test_legacy_cards_have_no_order_and_keep_original_insertion_order(self):
        source = original_state()
        snapshot = deepcopy(source)
        original_ids = [task["id"] for task in source["tasks"]]
        self.assertTrue(all("cardOrder" not in task for task in source["tasks"]))
        normalized = native_app.normalize_state(source)
        self.assertTrue(validate_plus(normalized))
        self.assertTrue(native_app.is_valid(normalized))
        self.assertEqual([task["id"] for task in normalized["tasks"]], original_ids)
        self.assertTrue(all("cardOrder" not in task for task in normalized["tasks"]))
        self.assertEqual(source, snapshot, "normalization modified its input")

    def test_integer_boundaries_and_lossless_financial_json_migration(self):
        source = original_state()
        financial_before = finance_snapshot(native_app.normalize_state(source))
        source["tasks"][0]["cardOrder"] = 0
        source["tasks"][1]["cardOrder"] = MAX_CARD_ORDER
        original_copy = deepcopy(source)
        migrated = native_app.normalize_state(source)
        self.assertTrue(validate_plus(migrated))
        self.assertTrue(native_app.is_valid(migrated))
        self.assertEqual(source, original_copy)
        self.assertEqual(finance_snapshot(migrated), financial_before)
        self.assertEqual([migrated["tasks"][i]["cardOrder"] for i in (0, 1)],
                         [0, MAX_CARD_ORDER])
        encoded = json.loads(json.dumps(migrated, ensure_ascii=False))
        self.assertEqual(normalize_plus(encoded), encoded)
        self.assertEqual(native_app.normalize_state(encoded), encoded)
        self.assertEqual(finance_snapshot(encoded), financial_before)

    def test_reject_malformed_and_unbounded_card_order_in_both_validators(self):
        """Reject out-of-bound and non-integer order on both host validators."""
        valid = native_app.normalize_state(original_state())
        invalid = [(-1, "negative"), (MAX_CARD_ORDER + 1, "overflow"),
                   (1.5, "fraction"), (True, "boolean-true"),
                   (False, "boolean-false"), ("7", "numeric-string"),
                   (None, "null"), ([], "list"), ({}, "object")]
        unguarded = []
        for validator in (validate_plus, native_app.is_valid):
            for value, label in invalid:
                state = deepcopy(valid)
                state["tasks"][0]["cardOrder"] = value
                before = deepcopy(state)
                try:
                    validator(state)
                except ValueError:
                    pass
                else:
                    unguarded.append(f"{validator.__module__}.{validator.__name__}:{label}")
                self.assertEqual(state, before, "validator mutated a rejected candidate")
        self.assertEqual(unguarded, [], "Python validators accepted invalid cardOrder: " +
                         ", ".join(unguarded))


class CardOrderDiskContractTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="madar-card-order-contract-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        env = patch.dict(os.environ, {"APPDATA": str(self.root),
                                   "LOCALAPPDATA": str(self.root)})
        env.start()
        self.addCleanup(env.stop)
        fake_datadir = patch.object(native_app, "datadir", return_value=self.root)
        fake_datadir.start()
        self.addCleanup(fake_datadir.stop)
        self.bridge = native_app.Bridge()
        # The disk parity cases explicitly use example-1 and p-sample;
        # initialize that disposable legacy fixture without seeding users.
        self.bridge.saveState(native_app.initial_state())

    def test_bridge_persists_order_and_finance_together_across_fresh_instance(self):
        state = self.bridge.getState()
        sample = next(p for p in state["projects"] if p["id"] == "p-sample")
        sample["price"] = 123_000_007
        task = next(t for t in state["tasks"] if t["id"] == "example-1")
        task.update(cardOrder=MAX_CARD_ORDER, cost=500_003, costEnabled=True)
        task["checklist"][0]["cost"] = 10_007
        expected = finance_snapshot(state)
        self.bridge.saveState(state)
        fresh = native_app.Bridge().getState()
        stored_task = next(t for t in fresh["tasks"] if t["id"] == "example-1")
        self.assertEqual(stored_task["cardOrder"], MAX_CARD_ORDER)
        self.assertEqual(finance_snapshot(fresh), expected)
        self.assertTrue(native_app.is_valid(fresh))

    def test_invalid_card_order_save_must_not_replace_previous_state(self):
        """Atomic invalid-write guard for malformed stored position."""
        before = self.bridge.path.read_bytes()
        invalid = self.bridge.getState()
        invalid["tasks"][0]["cardOrder"] = -1
        with self.assertRaisesRegex(ValueError, "cardOrder"):
            self.bridge.saveState(invalid)
        self.assertEqual(self.bridge.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
