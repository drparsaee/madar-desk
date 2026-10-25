"""Synthetic M02 two-client offline reconnect, no network or production data.

This confirms conservative record-level three-way merge on two independent
disposable offline stores, NOT full physical LAN or vector-clock acceptance.
"""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from offline_exchange import OfflineStore


def fixture(count=25):
    return {
        "version": 1,
        "settings": {},
        "stages": [],
        "workspaces": [],
        "boards": [],
        "projects": [{"id": "proj-1", "name": "test"}],
        "tasks": [
            {"id": f"task-{i:02d}", "projectId": "proj-1",
             "title": f"base-{i:02d}", "cost": 1_000_000+i}
            for i in range(count)
        ],
    }


class Reconnect25EditTests(unittest.TestCase):
    def test_two_clients_reconcile_25_nonoverlapping_edits_with_money_unchanged(self):
        with tempfile.TemporaryDirectory(prefix="madar-m02-two-client-") as root:
            a = OfflineStore(Path(root) / "client-a")
            b = OfflineStore(Path(root) / "client-b")
            original = fixture()
            left, right = deepcopy(original), deepcopy(original)
            a.remember(original, "r-0", "operator-a")
            b.remember(original, "r-0", "operator-b")
            for index in range(25):
                card = (left if index % 2 == 0 else right)["tasks"][index]
                card["title"] = f"offline-edit-{index:02d}"
            a.queue(left, "operator-a")
            b.queue(right, "operator-b")

            host = a.reconcile(deepcopy(original), "r-0", "operator-a")
            a.ack(host, "r-1", "operator-a")
            host = b.reconcile(host, "r-1", "operator-b")
            b.ack(host, "r-2", "operator-b")

            self.assertFalse(a.has_pending())
            self.assertFalse(b.has_pending())
            self.assertEqual(len(host["tasks"]), 25)
            self.assertEqual(
                [card["title"] for card in host["tasks"]],
                [f"offline-edit-{i:02d}" for i in range(25)])
            self.assertEqual(
                [card["cost"] for card in host["tasks"]],
                [card["cost"] for card in original["tasks"]])

    def test_overlapping_client_edits_explicitly_conflict_and_remain_pending(self):
        with tempfile.TemporaryDirectory(prefix="madar-m02-conflict-") as root:
            a = OfflineStore(Path(root) / "client-a")
            b = OfflineStore(Path(root) / "client-b")
            original = fixture()
            first, second = deepcopy(original), deepcopy(original)
            a.remember(original, "r-0", "operator-a")
            b.remember(original, "r-0", "operator-b")
            first["tasks"][0]["title"] = "changed-on-a"
            second["tasks"][0]["title"] = "changed-on-b"
            a.queue(first, "operator-a")
            b.queue(second, "operator-b")
            host = a.reconcile(deepcopy(original), "r-0", "operator-a")
            a.ack(host, "r-1", "operator-a")
            with self.assertRaisesRegex(RuntimeError, "CONFLICT"):
                b.reconcile(host, "r-1", "operator-b")
            self.assertTrue(b.has_pending())
            self.assertEqual(host["tasks"][0]["title"], "changed-on-a")
            self.assertEqual(b.get_cached()["tasks"][0]["title"], "changed-on-b")


if __name__ == "__main__":
    unittest.main()
