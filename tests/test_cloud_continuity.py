import copy
import json
import tempfile
import unittest
from pathlib import Path

from cloud_continuity import CloudConflict, PeerJournal


def sample():
    return {"projects": [{"id": "p1"}, {"id": "p2"}], "boards": [],
            "workspaces": [], "stages": [], "settings": {}, "templates": [],
            "tasks": [
                {"id": "a", "projectId": "p1", "title": "A", "fileLinks": [{"path": "\\\\Local\\Share\\file"}]},
                {"id": "b", "projectId": "p1", "title": "B", "fileLinks": []},
            ]}


class PeerJournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        folder = Path(self.tmp.name)
        common = ("host1", "member", "baserev", "an-adequately-long-pairing-secret-2026", ["p1"])
        self.a = PeerJournal(folder, *common, "device1")
        self.b = PeerJournal(folder, *common, "device2")
        self.base = sample()

    def test_two_devices_merge_unrelated_edits_and_keep_smb_local_only(self):
        one = copy.deepcopy(self.base)
        one["tasks"][0]["title"] = "first machine"
        self.a.append(self.base, one, anchor=self.base)
        two = copy.deepcopy(self.base)
        two["tasks"][1]["title"] = "second machine"
        self.b.append(self.base, two, anchor=self.base)
        merged_a, conflicts, clock = self.a.replay(self.base)
        merged_b, other_conflicts, _ = self.b.replay(self.base)
        self.assertFalse(conflicts)
        self.assertFalse(other_conflicts)
        self.assertEqual(merged_a, merged_b)
        self.assertEqual([t["title"] for t in merged_a["tasks"]], ["first machine", "second machine"])
        self.assertEqual(clock, 2)
        cloud_content = "\n".join(p.read_text("utf8") for p in self.a.folder.glob("*.json"))
        self.assertNotIn("Local", cloud_content)
        self.assertEqual(merged_a["tasks"][0]["fileLinks"], self.base["tasks"][0]["fileLinks"])

    def test_simultaneous_same_card_changes_are_a_reported_conflict(self):
        first = copy.deepcopy(self.base)
        first["tasks"][0]["title"] = "one"
        self.a.append(self.base, first, anchor=self.base)
        stale = copy.deepcopy(self.base)
        stale["tasks"][0]["title"] = "two"
        with self.assertRaisesRegex(CloudConflict, "CONFLICT"):
            self.b.append(self.base, stale, anchor=self.base)
        # A sync client may have committed an event before seeing a peer's.
        # Once both events arrive, replay reports the losing edit explicitly.
        record = self.a.events()[0]
        self.assertEqual(record["changes"][0]["after"]["title"], "one")

    def test_tampering_wrong_secret_and_different_user_are_rejected(self):
        modified = copy.deepcopy(self.base)
        modified["tasks"][0]["title"] = "changed"
        self.a.append(self.base, modified, anchor=self.base)
        forged = PeerJournal(Path(self.tmp.name), "host1", "member", "baserev",
                             "wrong-but-long-pairing-secret-2026", ["p1"], "third")
        with self.assertRaises(PermissionError):
            forged.events()
        path = next(self.a.folder.glob("*.json"))
        payload = json.loads(path.read_text("utf8"))
        payload["body"]["changes"][0]["after"]["title"] = "tampered"
        path.write_text(json.dumps(payload), "utf8")
        with self.assertRaises(PermissionError):
            self.a.events()

    def test_scope_structure_and_secret_are_enforced(self):
        with self.assertRaises(ValueError):
            PeerJournal(Path(self.tmp.name), "host1", "member", "baserev", "weak", ["p1"], "device")
        bad = copy.deepcopy(self.base)
        bad["tasks"][0]["projectId"] = "p2"
        with self.assertRaises(PermissionError):
            self.a.append(self.base, bad, anchor=self.base)
        bad = copy.deepcopy(self.base)
        bad["projects"].append({"id": "new"})
        with self.assertRaises(PermissionError):
            self.a.append(self.base, bad, anchor=self.base)


if __name__ == "__main__":
    unittest.main()
