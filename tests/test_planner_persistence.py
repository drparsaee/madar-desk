"""Disposable profile tests for the origin-independent Planner v1 data store."""

import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import planner_persistence as persistence
from planner_persistence import PlannerPersistence, PlannerPersistenceError


def planner(title="برنامه خصوصی", *, account_item="private-1"):
    return {"version": 1, "inbox": [{
        "id": account_item, "title": title, "notes": "یادداشت",
        "createdDate": "2026-10-28", "dueDate": "2028-02-29", "doneAt": "",
        "repeatAnchor": "2028-02-29", "remindTime": "09:05",
        "dismissedFor": "", "repeat": {"frequency": "monthly", "interval": 1,
                                        "calendar": "jalali"},
    }], "entries": [{
        "id": "entry-1", "source": "personal",
        "refId": account_item, "date": "2028-02-29",
    }]}


class PlannerPersistenceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="madar-planner-backend-qa-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "MadarDesk"
        self.root.mkdir()
        self.store = PlannerPersistence(self.root)

    def paths(self, account="solo"):
        return self.store._paths(account)

    def test_constructor_and_uninitialized_read_make_no_files(self):
        self.assertIsNone(self.store.read("solo"))
        self.assertFalse(self.store.folder.exists())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_browser_generated_account_namespaces_save_without_any_loss_or_collision(self):
        # These are the literal JSON.stringify values passed by App.jsx.
        identities = [
            '["solo","local"]',
            '["solo","alice"]',
            '["server","owner"]',
            '["client","http://127.0.0.1:48370","","alice"]',
            '["client","http://127.0.0.1:48371","","alice"]',
            '["client","https://host.example","' + "a" * 64 + '","alice"]',
            '["client","https://host.example/' + "long-" * 120 + '","","alice"]',
        ]
        self.store.write("solo", planner("old-legacy"))
        self.store.write("[legacy]", planner("old-bracket-legacy"))
        self.store.write("[1,2]", planner("old-array-shaped-legacy"))
        for index, identity in enumerate(identities):
            self.assertIsNone(self.store.read(identity), identity)
            self.assertEqual(self.store.write(identity, planner(f"private-{index}")),
                             planner(f"private-{index}"))
        self.assertEqual(self.store.read("solo"), planner("old-legacy"))
        self.assertEqual(self.store.read("[legacy]"), planner("old-bracket-legacy"))
        self.assertEqual(self.store.read("[1,2]"), planner("old-array-shaped-legacy"))
        self.assertEqual(len({self.store._paths(identity)[0] for identity in identities}), len(identities))
        for index, identity in enumerate(identities):
            self.assertEqual(PlannerPersistence(self.root).read(identity),
                             planner(f"private-{index}"))

    def test_malformed_structured_account_is_rejected_before_writing(self):
        invalid = [
            '["solo"]', '["unknown","local"]', '["client","https://host","alice"]',
            '["client","file:///secret","","alice"]', '["client","","","alice"]',
            '["client","https://host","",null]', '["solo",12]',
            '{"mode":"solo","username":"local"}', '["solo",""]',
            '["solo","bad\\nname"]', '["solo","\\ud800"]',
            '["client","https://host","", "alice", "extra"]',
            '["client","https://host","",' + '"x"' * 2100 + ']',
            '["solo","' + "a" * 4100 + '"]',
        ]
        for account in invalid:
            with self.subTest(account=account[:60]), self.assertRaises(ValueError):
                self.store.write(account, planner("never-written"))
        self.assertFalse(self.store.folder.exists())

    def test_round_trip_survives_new_process_store_instance_and_separates_accounts(self):
        expected = planner()
        self.assertEqual(self.store.write("solo", expected), expected)
        active, previous, _lock = self.paths()
        self.assertTrue(active.is_file())
        self.assertFalse(previous.exists())
        self.assertNotIn("solo", active.name)
        restarted = PlannerPersistence(self.root)
        self.assertEqual(restarted.read("solo"), expected)
        self.assertIsNone(restarted.read("other"))
        restarted.write("other", planner("شخص دیگری"))
        self.assertEqual(self.store.read("solo"), expected)
        self.assertEqual(self.store.read("other")["inbox"][0]["title"],
                         "شخص دیگری")

    def test_legacy_planner_v1_repetition_and_defaults_normalize_without_losing_data(self):
        original = planner()
        item = original["inbox"][0]
        for key in ("notes", "repeatAnchor", "remindTime", "dismissedFor"):
            del item[key]
        item["repeat"] = "none"
        saved = self.store.write("solo", original)
        self.assertEqual(saved["inbox"][0]["repeat"], {
            "frequency": "none", "interval": 1, "calendar": "gregorian"})
        self.assertEqual(saved["inbox"][0]["repeatAnchor"], item["dueDate"])
        self.assertEqual(saved["inbox"][0]["notes"], "")
        self.assertEqual(self.store.read("solo"), saved)

    def test_second_write_keeps_previous_valid_revision_and_noop_does_not_rotate(self):
        before = planner("اول")
        after = planner("دوم")
        self.store.write("solo", before)
        self.store.write("solo", after)
        active, previous, _ = self.paths()
        self.assertEqual(json.loads(previous.read_text("utf8")), before)
        old_bytes = previous.read_bytes()
        self.assertEqual(self.store.read("solo"), after)
        self.store.write("solo", after)
        self.assertEqual(previous.read_bytes(), old_bytes)
        self.assertEqual(json.loads(active.read_text("utf8")), after)

    def test_invalid_input_and_bad_account_never_touch_existing_saved_state(self):
        before = planner()
        self.store.write("solo", before)
        active, previous, _ = self.paths()
        first_bytes = active.read_bytes()
        for account in ("", "   ", "../other", "person/name", "p\\name",
                        "..", "a" * 121, "invalid\x00user"):
            with self.subTest(account=repr(account)), self.assertRaises(ValueError):
                self.store.write(account, before)
        bad_states = [
            {"version": 99, "inbox": [], "entries": []},
            {"version": 1, "inbox": "wrong", "entries": []},
            {**before, "extraFutureField": "valuable"},
            {**before, "inbox": [before["inbox"][0]] * 2},
            {**before, "inbox": [{**before["inbox"][0], "dueDate": "2026-02-29"}]},
            {**before, "inbox": [{**before["inbox"][0], "remindTime": "26:00"}]},
            {**before, "inbox": [{**before["inbox"][0], "repeat": {
                "frequency": "daily", "interval": True}}]},
            {**before, "inbox": [{**before["inbox"][0], "newField": "must not drop"}]},
            {**before, "entries": [{**before["entries"][0], "date": "2026-13-01"}]},
        ]
        for invalid in bad_states:
            with self.subTest(state=invalid), self.assertRaises(ValueError):
                self.store.write("solo", invalid)
        self.assertEqual(active.read_bytes(), first_bytes)
        self.assertFalse(previous.exists())
        self.assertEqual(self.store.read("solo"), before)

    def test_corrupt_primary_and_missing_primary_fail_closed_preserve_previous(self):
        before, after = planner("اول"), planner("دوم")
        self.store.write("solo", before)
        self.store.write("solo", after)
        active, previous, _ = self.paths()
        saved_previous = previous.read_bytes()
        active.write_text('{"version":1,"inbox":[],"entries":[],"version":1}',
                          encoding="utf8")
        with self.assertRaises(PlannerPersistenceError):
            self.store.read("solo")
        with self.assertRaises(PlannerPersistenceError):
            self.store.write("solo", planner("سوم"))
        self.assertEqual(previous.read_bytes(), saved_previous)
        active.unlink()
        with self.assertRaises(PlannerPersistenceError):
            self.store.read("solo")
        with self.assertRaises(PlannerPersistenceError):
            self.store.write("solo", planner("چهارم"))
        self.assertEqual(previous.read_bytes(), saved_previous)

    def test_failure_replacing_primary_leaves_old_and_recovery_snapshot_valid(self):
        before = planner("قبل")
        self.store.write("solo", before)
        active, previous, _ = self.paths()
        real_replace = os.replace

        def fail_active(src, dst):
            if Path(dst) == active:
                raise OSError("simulated destination full")
            return real_replace(src, dst)

        with patch.object(persistence.os, "replace", side_effect=fail_active):
            with self.assertRaisesRegex(OSError, "destination full"):
                self.store.write("solo", planner("بعد"))
        self.assertEqual(self.store.read("solo"), before)
        self.assertEqual(json.loads(previous.read_text(encoding="utf8")), before)
        self.assertEqual(list(self.store.folder.glob("*.tmp")), [])

    def test_directory_and_primary_links_are_refused_when_platform_supports_them(self):
        outside = self.root / "outside.json"
        outside.write_text("private", encoding="utf8")
        self.store.folder.mkdir()
        active, _, _ = self.paths()
        try:
            active.symlink_to(outside)
        except (NotImplementedError, OSError):
            self.skipTest("Symlinks unavailable to this Windows account")
        with self.assertRaises(PlannerPersistenceError):
            self.store.read("solo")
        with self.assertRaises(PlannerPersistenceError):
            self.store.write("solo", planner())
        self.assertEqual(outside.read_text("utf8"), "private")

    def test_two_store_instances_concurrent_writes_leave_valid_primary_and_previous(self):
        self.store.write("solo", planner("base"))
        gate = threading.Barrier(3)
        outcomes = []

        def worker(label):
            try:
                gate.wait(timeout=3)
                outcomes.append(PlannerPersistence(self.root).write("solo", planner(label)))
            except Exception as error:
                outcomes.append(error)

        threads = [threading.Thread(target=worker, args=(label,))
                   for label in ("first", "second")]
        for thread in threads:
            thread.start()
        gate.wait(timeout=3)
        for thread in threads:
            thread.join(timeout=5)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(len(outcomes), 2)
        self.assertTrue(all(isinstance(outcome, dict) for outcome in outcomes), outcomes)
        active, previous, _ = self.paths()
        self.assertIn(self.store.read("solo")["inbox"][0]["title"],
                      {"first", "second"})
        self.assertIn(json.loads(previous.read_text("utf8"))["inbox"][0]["title"],
                      {"base", "first", "second"})
        self.assertNotEqual(json.loads(active.read_text("utf8")),
                            json.loads(previous.read_text("utf8")))

    def test_root_requirement_and_oversize_data_fail_before_writing(self):
        missing = PlannerPersistence(self.root / "missing")
        with self.assertRaises(PlannerPersistenceError):
            missing.read("solo")
        with self.assertRaises(PlannerPersistenceError):
            missing.write("solo", planner())
        self.assertFalse((self.root / "missing").exists())
        with patch.object(persistence, "MAX_STATE_BYTES", 32):
            with self.assertRaisesRegex(ValueError, "limit"):
                self.store.write("solo", planner())
        self.assertFalse(self.store.folder.exists())


if __name__ == "__main__":
    unittest.main()
