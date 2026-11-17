"""Synthetic Windows fault probes for manual Taraz metadata retries.

Only uses a TemporaryDirectory redirected through LOCALAPPDATA. In particular,
neither a real Madar/Taraz profile nor an accounting ledger is opened.

A non-cooperating local writer bypassing the documented OS lock is outside the
cooperative Madar/Taraz delivery contract. These tests identify that boundary
without misrepresenting local observations as verified accounting receipts.
"""

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from taraz_exchange import _request_lock, queue_saved_task
from taraz_review_status import local_task_reviews


class ManualRetryFaultTests(unittest.TestCase):
    REQUEST = "d" * 32

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mtr-retry-fault-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "Madar-Taraz-Bridge"
        env = patch.dict(os.environ, {"LOCALAPPDATA": temporary.name})
        env.start()
        self.addCleanup(env.stop)
        self.state = {
            "tasks": [
                {
                    "id": "synthetic-task",
                    "projectId": "synthetic-project",
                    "title": "Synthetic selected work",
                    "checklist": [],
                }
            ]
        }

    def queue(self):
        return queue_saved_task(
            self.state, "synthetic-task", request_id=self.REQUEST
        )

    def test_real_windows_hard_link_contention_has_single_winner(self):
        """Prove exclusive filesystem creation independently of sender locks."""
        folder = self.root / "pending"
        folder.mkdir(parents=True)
        first = folder / "one.tmp"
        second = folder / "two.tmp"
        target = folder / (self.REQUEST + ".json")
        first.write_bytes(b"first synthetic source")
        second.write_bytes(b"second synthetic source")
        publication_barrier = threading.Barrier(2, timeout=10)

        def simultaneous_link(source):
            publication_barrier.wait()
            try:
                os.link(source, target)
                return "published"
            except FileExistsError:
                return "occupied"

        with ThreadPoolExecutor(max_workers=2) as executor:
            a = executor.submit(simultaneous_link, first)
            b = executor.submit(simultaneous_link, second)
            outcomes = [a.result(timeout=15), b.result(timeout=15)]
        self.assertEqual(sorted(outcomes), ["occupied", "published"])
        self.assertIn(target.read_bytes(), (first.read_bytes(), second.read_bytes()))

    def test_two_concurrent_inprocess_manual_retries_are_serialized(self):
        """Both senders use the same ID; one publishes and one safely replays."""
        start = threading.Barrier(2, timeout=10)

        def send():
            start.wait()
            return self.queue()

        with ThreadPoolExecutor(max_workers=2) as executor:
            a = executor.submit(send)
            b = executor.submit(send)
            outcomes = [a.result(timeout=15), b.result(timeout=15)]
        self.assertEqual(sorted(result["queued"] for result in outcomes), [False, True])
        self.assertEqual(sorted(result["replayed"] for result in outcomes), [False, True])
        self.assertEqual(len(list((self.root / "pending").glob("*.json"))), 1)
        self.assertEqual(list((self.root / "pending").glob("*.tmp")), [])

    def test_stale_lock_without_proposal_does_not_permit_resend(self):
        """An abandoned request ID has an unknown outcome after a crash."""
        reviewed = self.root / "reviewed"
        with _request_lock(reviewed, self.REQUEST):
            pass
        with self.assertRaises(RuntimeError):
            self.queue()
        self.assertFalse((self.root / "pending" / (self.REQUEST + ".json")).exists())

    def test_cross_process_taraz_lock_prevents_interleaved_requeue(self):
        """Second Windows process waits until the reviewed proposal is visible."""
        reviewed = self.root / "reviewed"
        reviewed.mkdir(parents=True)
        marker = self.root / "child-ready.marker"
        code = (
            "import json, os, pathlib\n"
            "from taraz_exchange import queue_saved_task\n"
            "pathlib.Path(os.environ['MTR_READY']).write_text('ready')\n"
            "state={'tasks':[{'id':'synthetic-task','projectId':'synthetic-project',"
            "'title':'Synthetic selected work','checklist':[]}]}\n"
            "print(json.dumps(queue_saved_task(state,'synthetic-task',"
            "request_id='d'*32)),flush=True)\n"
        )
        child = None
        try:
            with _request_lock(reviewed, self.REQUEST):
                child = subprocess.Popen(
                    [sys.executable, "-B", "-c", code],
                    cwd=str(Path(__file__).resolve().parents[1]),
                    env=dict(os.environ, MTR_READY=str(marker)),
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True,
                )
                deadline = time.monotonic() + 5
                while not marker.exists() and time.monotonic() < deadline:
                    if child.poll() is not None:
                        break
                    time.sleep(0.02)
                self.assertTrue(marker.exists(), "Child never attempted the shared lock")
                self.assertIsNone(child.poll(), "Child crossed a held review lock")
                record = {
                    "schema": 1, "source": "madar", "id": self.REQUEST,
                    "taskId": "synthetic-task", "title": "Synthetic selected work",
                    "projectId": "synthetic-project",
                    "createdUtc": "2026-11-09T00:00:00+00:00",
                }
                (reviewed / (self.REQUEST + ".json")).write_text(
                    json.dumps(record), encoding="utf8"
                )
            output, error = child.communicate(timeout=15)
            self.assertEqual(child.returncode, 0, error)
            result = json.loads(output)
            self.assertTrue(result["replayed"])
            self.assertFalse(result["queued"])
            self.assertEqual(result["observedLocation"], "reviewed")
            self.assertFalse((self.root / "pending" / (self.REQUEST + ".json")).exists())
        finally:
            if child is not None and child.poll() is None:
                child.kill()
                child.communicate(timeout=10)

    def test_after_publication_fault_can_be_replayed_without_second_file(self):
        """Crash after a successful link means the caller saw an uncertain send."""
        original_link = os.link

        def commit_then_crash(source, target):
            original_link(source, target)
            raise OSError("synthetic crash immediately after publication")

        with patch("taraz_exchange.os.link", side_effect=commit_then_crash):
            with self.assertRaisesRegex(OSError, "synthetic crash"):
                self.queue()

        inbox = self.root / "pending"
        self.assertEqual(len(list(inbox.glob("*.json"))), 1)
        self.assertEqual(list(inbox.glob("*.tmp")), [])
        replay = self.queue()
        self.assertTrue(replay["replayed"])
        self.assertFalse(replay["queued"])
        self.assertFalse(replay["postingPerformed"])

    def test_unsupported_link_failure_leaves_no_partial_request(self):
        with patch("taraz_exchange.os.link", side_effect=OSError("unsupported")):
            with self.assertRaisesRegex(OSError, "unsupported"):
                self.queue()
        inbox = self.root / "pending"
        self.assertEqual(list(inbox.glob("*.json")), [])
        self.assertEqual(list(inbox.glob("*.tmp")), [])

    def test_noncooperating_writer_makes_conflicting_local_status_unknown(self):
        """A writer bypassing the shared lock can still produce ambiguous data."""
        original_link = os.link

        def review_wins_before_publication(source, target):
            reviewed = self.root / "reviewed"
            reviewed.mkdir(parents=True, exist_ok=True)
            (reviewed / (self.REQUEST + ".json")).write_bytes(Path(source).read_bytes())
            return original_link(source, target)

        with patch("taraz_exchange.os.link", side_effect=review_wins_before_publication):
            result = self.queue()

        self.assertTrue(result["queued"])
        self.assertFalse(result["postingPerformed"])
        self.assertTrue((self.root / "pending" / (self.REQUEST + ".json")).exists())
        self.assertTrue((self.root / "reviewed" / (self.REQUEST + ".json")).exists())
        observed = local_task_reviews(
            "synthetic-task", "synthetic-project", opted_in=True, root=self.root
        )
        self.assertEqual(observed["items"][0]["state"], "unknown")
        self.assertFalse(observed["peerVerified"])
        self.assertFalse(observed["postingEnabled"])

    def test_malformed_local_created_utc_must_not_crash_status_inspection(self):
        """A malformed local proposal must not cause an unhandled KeyError."""
        pending = self.root / "pending"
        pending.mkdir(parents=True)
        record = {
            "schema": 1,
            "source": "madar",
            "id": self.REQUEST,
            "taskId": "synthetic-task",
            "projectId": "synthetic-project",
            "title": "Synthetic selected work",
        }
        (pending / (self.REQUEST + ".json")).write_text(
            json.dumps(record), encoding="utf8"
        )
        observed = local_task_reviews(
            "synthetic-task", "synthetic-project", opted_in=True, root=self.root
        )
        self.assertIn(observed["state"], ("unavailable", "partial", "observed"))
        self.assertEqual(observed["items"], [])


if __name__ == "__main__":
    unittest.main()
