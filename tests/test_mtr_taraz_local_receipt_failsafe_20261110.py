"""Disposable regression: a local file is never authenticated Taraz authority."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from taraz_review_status import local_task_reviews


REQUEST = "a" * 32
TASK = "task-synthetic"
PROJECT = "project-synthetic"


class FailClosedLocalReview(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="mtr-review-failsafe-qa-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "Madar-Taraz-Bridge"
        self.reviewed = self.root / "reviewed"
        self.reviewed.mkdir(parents=True)
        self.original = self.reviewed / (REQUEST + ".json")
        self.receipt = self.reviewed / (REQUEST + ".review.json")
        self.intent = self.reviewed / (REQUEST + ".intent.json")
        self.proposal = {
            "schema": 1, "source": "madar", "id": REQUEST, "taskId": TASK,
            "projectId": PROJECT, "title": "Synthetic nonfinancial card",
            "createdUtc": "2026-11-10T12:00:00+00:00",
        }
        self.raw = json.dumps(self.proposal, ensure_ascii=False).encode("utf-8")
        self.original.write_bytes(self.raw)
        self.marker = {
            "schema": 1, "id": REQUEST, "source": "taraz",
            "state": "reviewed", "reviewedUtc": "2026-11-10T12:01:00+00:00",
            "taskId": TASK, "financialEventCreated": False,
        }
        self.receipt.write_text(json.dumps(self.marker), encoding="utf-8")
        self.intent.write_text(json.dumps({
            **self.marker, "sourceDigest": hashlib.sha256(self.raw).hexdigest(),
        }), encoding="utf-8")

    def observe(self):
        result = local_task_reviews(TASK, PROJECT, opted_in=True, root=self.root)
        self.assertIs(result["peerVerified"], False)
        self.assertIs(result["postingEnabled"], False)
        self.assertEqual(len(result["items"]), 1)
        self.assertIs(result["items"][0]["financialEventCreated"], False)
        return result["items"][0]["state"]

    def test_source_bound_local_intent_only_reports_nonfinancial_review(self):
        self.assertEqual(self.observe(), "reviewed")

    def test_legacy_review_receipt_without_intent_is_unknown(self):
        self.intent.unlink()
        self.assertEqual(self.observe(), "unknown")

    def test_intent_digest_mismatch_is_unknown(self):
        data = json.loads(self.intent.read_text(encoding="utf-8"))
        data["sourceDigest"] = "0" * 64
        self.intent.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(self.observe(), "unknown")

    def test_duplicate_keys_are_not_accepted(self):
        self.intent.write_text('{"schema":1,"schema":1}', encoding="utf-8")
        self.assertEqual(self.observe(), "unknown")

    def test_receipt_with_duplicate_keys_is_not_accepted(self):
        raw = self.receipt.read_text(encoding="utf-8")
        self.receipt.write_text(raw[:-1] + ',"schema":1}', encoding="utf-8")
        self.assertEqual(self.observe(), "unknown")

    def test_mutated_proposal_cannot_inherit_old_decision(self):
        self.original.write_bytes(self.raw.replace(b"Synthetic", b"Changed__"))
        self.assertEqual(self.observe(), "unknown")

    def test_financial_marker_is_refused(self):
        self.marker["financialEventCreated"] = True
        self.receipt.write_text(json.dumps(self.marker), encoding="utf-8")
        self.assertEqual(self.observe(), "unknown")

    def test_unexpected_intent_field_is_unknown(self):
        intent = json.loads(self.intent.read_text(encoding="utf-8"))
        intent["peerVerified"] = True
        self.intent.write_text(json.dumps(intent), encoding="utf-8")
        self.assertEqual(self.observe(), "unknown")

    def test_hard_linked_receipt_is_unknown(self):
        extra = self.reviewed / "separate-hard-link.json"
        try:
            extra.hardlink_to(self.receipt)
        except OSError:
            self.skipTest("Platform denies local hard links")
        self.assertEqual(self.observe(), "unknown")


if __name__ == "__main__":
    unittest.main()
