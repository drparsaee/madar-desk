"""Synthetic first-send journal tests; never operate on real APPDATA or finance."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mtr_e2_send_journal import prepare_manual_send
from mtr_e2_send_journal import assert_prepared_matches_if_present
from taraz_exchange import queue_saved_task
import native_app


class DurableFirstSendTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mtr-first-send-")
        self.addCleanup(temporary.cleanup)
        env = patch.dict(os.environ, {"LOCALAPPDATA": temporary.name})
        env.start()
        self.addCleanup(env.stop)
        self.root = Path(temporary.name) / "Madar-Taraz-Bridge"
        self.state = {"tasks": [{
            "id": "synthetic-task", "projectId": "synthetic-project",
            "title": "Synthetic packaging proposal", "checklist": []
        }]}

    def prep(self, **kwargs):
        return prepare_manual_send(self.state, "synthetic-task",
                                   actor_scope="client:test-user", **kwargs)

    def test_preparation_is_durable_and_does_not_transmit(self):
        first = self.prep()
        self.assertTrue(first["prepared"])
        self.assertFalse(first["reused"])
        self.assertFalse(first["postingPerformed"])
        self.assertFalse((self.root / "pending").exists())
        records = list((self.root / "send-intents").glob("*.json"))
        self.assertEqual(len(records), 1)
        record = json.loads(records[0].read_text(encoding="utf8"))
        self.assertEqual(record["requestId"], first["id"])
        self.assertNotIn("Synthetic packaging proposal", records[0].read_text(encoding="utf8"))
        second = self.prep()
        self.assertEqual(second["id"], first["id"])
        self.assertTrue(second["reused"])
        self.assertEqual(len(list((self.root / "send-intents").glob("*.json"))), 1)

    def test_manual_send_after_prepare_replays_with_same_id(self):
        intent = self.prep()
        posted = queue_saved_task(self.state, "synthetic-task",
                                  request_id=intent["id"])
        self.assertTrue(posted["queued"])
        second = self.prep()
        self.assertEqual(second["id"], posted["id"])
        replayed = queue_saved_task(self.state, "synthetic-task",
                                   request_id=second["id"])
        self.assertTrue(replayed["replayed"])
        self.assertFalse(replayed["queued"])
        self.assertEqual(len(list((self.root / "pending").glob("*.json"))), 1)

    def test_prepared_payload_must_match_before_first_send(self):
        intent = self.prep()
        self.assertTrue(assert_prepared_matches_if_present(
            self.state, "synthetic-task", None, actor_scope="client:test-user",
            request_id=intent["id"])["hasPreparedIntent"])
        self.state["tasks"][0]["title"] = "Data changed before native queue"
        with self.assertRaises(PermissionError):
            assert_prepared_matches_if_present(
                self.state, "synthetic-task", None, actor_scope="client:test-user",
                request_id=intent["id"])
        with self.assertRaises(PermissionError):
            assert_prepared_matches_if_present(
                self.state, "synthetic-task", None, actor_scope="client:test-user",
                request_id="f" * 32)
        self.assertFalse((self.root / "pending").exists())

    def test_changed_task_or_expense_cannot_reuse_old_approval(self):
        first = self.prep()
        self.state["tasks"][0]["title"] = "Changed after preparing"
        with self.assertRaises(ValueError):
            self.prep()
        self.assertFalse((self.root / "pending").exists())
        self.assertEqual(
            first["id"], json.loads(next((self.root / "send-intents").glob("*.json"))
                                    .read_text(encoding="utf8"))["requestId"])

    def test_separate_actor_has_separate_scoped_intent(self):
        first = self.prep()
        another = prepare_manual_send(self.state, "synthetic-task",
                                      actor_scope="client:other-user")
        self.assertNotEqual(first["id"], another["id"])
        self.assertEqual(len(list((self.root / "send-intents").glob("*.json"))), 2)

    def test_corrupt_record_fails_closed(self):
        self.prep()
        path = next((self.root / "send-intents").glob("*.json"))
        path.write_text('{"schemaVersion":1,"schemaVersion":1}', encoding="utf8")
        with self.assertRaises((ValueError, PermissionError)):
            self.prep()

    def test_symlinked_intent_directory_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="mtr-external-") as outside:
            self.root.mkdir()
            try:
                (self.root / "send-intents").symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("No symlink privileges")
            with self.assertRaises(PermissionError):
                self.prep()
            self.assertEqual(list(Path(outside).iterdir()), [])

    def test_invalid_actor_is_rejected_without_files(self):
        for actor in ("", "abc/../../", " " * 3, None, True):
            with self.subTest(actor=actor), self.assertRaises(ValueError):
                prepare_manual_send(self.state, "synthetic-task", actor_scope=actor)
        self.assertFalse(self.root.exists())

    def test_fault_after_exclusive_publication_reuses_original_id(self):
        actual = os.link
        def crash_after_commit(src, dst):
            actual(src, dst)
            raise OSError("simulated loss of prepare reply")
        with patch("mtr_e2_send_journal.os.link", side_effect=crash_after_commit):
            with self.assertRaisesRegex(OSError, "simulated loss"):
                self.prep()
        prior = json.loads(next((self.root / "send-intents").glob("*.json"))
                           .read_text(encoding="utf8"))
        self.assertEqual(self.prep()["id"], prior["requestId"])
        self.assertFalse((self.root / "pending").exists())
        self.assertEqual(list((self.root / "send-intents").glob("*.tmp")), [])

    def test_native_first_send_is_prepared_before_queue_and_reused(self):
        sandbox = self.root / "native-profile"
        sandbox.mkdir(parents=True, exist_ok=True)
        with patch.object(native_app, "datadir", return_value=sandbox):
            bridge = native_app.Bridge()
        bridge.connection = {"mode": "solo"}
        with patch.object(bridge, "getState", return_value=native_app.initial_state()):
            intent = bridge.tarazIntegrationPrepare("example-2")
            self.assertTrue(intent["prepared"])
            self.assertFalse((self.root / "pending").exists())
            result = bridge.tarazIntegrationQueue("example-2", None, intent["id"])
            self.assertTrue(result["queued"])
            repeated = bridge.tarazIntegrationPrepare("example-2")
            self.assertEqual(repeated["id"], intent["id"])
            replay = bridge.tarazIntegrationQueue("example-2", None, repeated["id"])
            self.assertTrue(replay["replayed"])
            self.assertFalse(replay["queued"])


if __name__ == "__main__":
    unittest.main()
