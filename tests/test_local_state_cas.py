"""P0 acceptance contract: solo Bridge must reject stale whole-state writes.

These intentionally RED regression tests use only a disposable shared root.
Two independent Bridge instances model two open local windows/processes that
already read the same state before one saves. Never access real APPDATA.

Run:
    py -3.12 -m unittest tests.test_local_state_cas -v

The expected current failure is an actual lost update, including a lost cost;
direct app_storage SQLite CAS is separately exercised as a positive control.
"""

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import tempfile
from threading import Barrier
import unittest
from unittest.mock import patch

from app_storage import RevisionConflict, UnifiedAppStorage
import native_app


FIRST_ID = "example-2"
SECOND_ID = "example-3"
FIRST_TITLE = "CAS protected first writer"
SECOND_TITLE = "Stale second writer"
FIRST_COST = 991_007
FIRST_PRICE = 6_250_000


def card(state, identifier):
    return next(item for item in state["tasks"] if item["id"] == identifier)


class LocalCASFixture(unittest.TestCase):
    """Isolated root is *only* shared by Bridges inside the same test method."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="madar-local-cas-solo-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        assert self.root.is_dir()

        # Belt and suspenders: neither normal datadir nor its environment can
        # resolve to the user's actual profile, even if a module calls either.
        environment = patch.dict(os.environ, {
            "APPDATA": str(self.root),
            "LOCALAPPDATA": str(self.root),
        })
        environment.start()
        self.addCleanup(environment.stop)
        isolated_datadir = patch.object(native_app, "datadir", return_value=self.root)
        isolated_datadir.start()
        self.addCleanup(isolated_datadir.stop)

        self.first = native_app.Bridge()
        self._assert_safe_bridge(self.first)
        self.assertEqual(self.first.connection.get("mode"), "solo")

    def _assert_safe_bridge(self, bridge):
        """Fail before a save if a path ever escapes the disposable test root."""
        for path in (bridge.path, bridge.unified_path, bridge.unified_marker,
                     bridge.collab_path, bridge.finance_path,
                     bridge.finance_outbox_path, bridge.automation_outbox_path):
            self.assertEqual(path.resolve().parent, self.root)
        self.assertEqual(bridge.backups_dir.resolve().parent, self.root)

    def _two_bridges(self, sqlite=False):
        if sqlite:
            migrated = self.first.enableUnifiedStorage()
            self.assertEqual(migrated["mode"], "sqlite")
        second = native_app.Bridge()
        self._assert_safe_bridge(second)
        self.assertIsNot(self.first, second)
        self.assertIsNot(self.first._lock, second._lock)
        self.assertEqual(self.first.path, second.path)
        self.assertEqual(self.first.unified_path, second.unified_path)
        self.assertEqual(second.connection.get("mode"), "solo")
        self.assertEqual(self.first.storageStatus()["mode"], "sqlite" if sqlite else "json")
        self.assertEqual(second.storageStatus()["mode"], "sqlite" if sqlite else "json")
        return self.first, second

    def _ui_state(self, bridge):
        """Read an editing snapshot with its attached local CAS baseline."""
        self.assertTrue(callable(getattr(bridge, "getStateForUi", None)),
            "P0: Bridge.getStateForUi() must expose an isolated UI snapshot")
        return deepcopy(bridge.getStateForUi())

    def _assert_issued_local_revision(self, sqlite):
        first, second = self._two_bridges(sqlite=sqlite)
        for bridge in (first, second):
            raw = bridge.getState()
            self.assertNotIn("__localRevision", raw,
                "Backend getState() must remain metadata-free for LAN and backups")
        state_a = self._ui_state(first)
        state_b = self._ui_state(second)
        token_a = state_a.get("__localRevision")
        token_b = state_b.get("__localRevision")
        self.assertIsInstance(token_a, str,
            "P0: solo getStateForUi must issue an opaque __localRevision CAS token")
        self.assertTrue(token_a,
            "P0: missing local revision cannot be used for optimistic concurrency")
        self.assertEqual(token_a, token_b,
            "Both readers must see the same revision of unchanged shared state")
        self.assertNotIn("__remoteRevision", state_a,
            "A local revision must never impersonate LAN synchronization")
        self.assertNotIn("__offline", state_a,
            "Solo local Bridge state is not an offline LAN cache")

    def _assert_missing_revision_fails_closed(self, sqlite):
        """A caller cannot bypass optimistic concurrency by omitting token."""
        first, _second = self._two_bridges(sqlite=sqlite)
        snapshot = self._ui_state(first)
        snapshot.pop("__localRevision", None)
        original = card(snapshot, FIRST_ID)["title"]
        card(snapshot, FIRST_ID)["title"] = "Unversioned save must be rejected"
        baseline = (UnifiedAppStorage(first.unified_path).load().revision if sqlite
                    else first.path.read_bytes())
        error = None
        try:
            first.saveState(snapshot)
        except (RuntimeError, ValueError) as exc:
            error = exc
        current = native_app.Bridge()
        self._assert_safe_bridge(current)
        self.assertEqual(card(current.getState(), FIRST_ID)["title"], original,
            "P0 CAS BYPASS: a local save without expected revision mutated state")
        self.assertIsNotNone(error,
            "Local saveState must refuse snapshots missing __localRevision")
        self.assertIn("CONFLICT", str(error),
            "Missing local revision must have distinguishable conflict semantics")
        after = (UnifiedAppStorage(first.unified_path).load().revision if sqlite
                 else first.path.read_bytes())
        self.assertEqual(after, baseline,
            "Rejected unversioned write must not modify backend storage")

    def _assert_no_stale_save(self, sqlite):
        first, second = self._two_bridges(sqlite=sqlite)
        first_snapshot = self._ui_state(first)
        second_snapshot = self._ui_state(second)
        self.assertEqual(card(first_snapshot, FIRST_ID)["title"],
                         card(second_snapshot, FIRST_ID)["title"])

        # The first writer owns a card AND a finance field. The stale second
        # reader changes a DIFFERENT card, so naive whole-state replacement
        # will silently roll back the unrelated first writer's edits.
        card(first_snapshot, FIRST_ID)["title"] = FIRST_TITLE
        card(first_snapshot, FIRST_ID)["cost"] = FIRST_COST
        sample_project = next(p for p in first_snapshot["projects"]
                              if p["id"] == "p-sample")
        sample_project["price"] = FIRST_PRICE
        card(second_snapshot, SECOND_ID)["title"] = SECOND_TITLE

        first.saveState(first_snapshot)
        saved = native_app.Bridge()
        self._assert_safe_bridge(saved)
        committed = deepcopy(saved.getState())
        self.assertEqual(card(committed, FIRST_ID)["title"], FIRST_TITLE)
        self.assertEqual(card(committed, FIRST_ID)["cost"], FIRST_COST)
        self.assertEqual(next(p for p in committed["projects"]
                              if p["id"] == "p-sample")["price"], FIRST_PRICE)
        json_before_stale = first.path.read_bytes() if not sqlite else None
        sql_before_stale = (UnifiedAppStorage(first.unified_path).load().revision
                            if sqlite else None)

        error = None
        try:
            second.saveState(second_snapshot)
        except (RuntimeError, ValueError) as exc:
            error = exc

        authoritative = native_app.Bridge()
        self._assert_safe_bridge(authoritative)
        actual = authoritative.getState()
        first_writer_payload = {
            "title": card(actual, FIRST_ID)["title"],
            "cost": card(actual, FIRST_ID)["cost"],
            "price": next(p for p in actual["projects"]
                          if p["id"] == "p-sample")["price"],
        }
        self.assertEqual(first_writer_payload, {
            "title": FIRST_TITLE, "cost": FIRST_COST, "price": FIRST_PRICE,
        }, "P0 LOST UPDATE: stale solo save erased first writer's task and finance edits")
        self.assertNotEqual(card(actual, SECOND_ID)["title"], SECOND_TITLE,
            "Stale second write should not reach disk before conflict resolution")

        self.assertIsNotNone(error,
            "P0: stale second Bridge saveState must raise a conflict")
        self.assertIn("CONFLICT", str(error),
            "Caller must receive a distinguishable CAS conflict")
        if sqlite:
            self.assertEqual(UnifiedAppStorage(first.unified_path).load().revision,
                             sql_before_stale,
                "A rejected stale write must not advance the SQLite revision")
        else:
            self.assertEqual(first.path.read_bytes(), json_before_stale,
                "A rejected stale write must not replace the JSON state")


class LocalCASRevisionContractTests(LocalCASFixture):
    def test_json_get_state_for_ui_issues_stable_cas_revision(self):
        self._assert_issued_local_revision(sqlite=False)

    def test_sqlite_get_state_for_ui_issues_stable_cas_revision(self):
        self._assert_issued_local_revision(sqlite=True)

    def test_json_save_requires_caller_provided_local_revision(self):
        self._assert_missing_revision_fails_closed(sqlite=False)

    def test_sqlite_save_requires_caller_provided_local_revision(self):
        self._assert_missing_revision_fails_closed(sqlite=True)

    def test_json_stale_second_bridge_must_not_erase_first_writer(self):
        self._assert_no_stale_save(sqlite=False)

    def test_sqlite_stale_second_bridge_must_not_erase_first_writer(self):
        self._assert_no_stale_save(sqlite=True)


class LocalCASConcurrentThreadTests(LocalCASFixture):
    """Actual overlapping saves by separate Bridge objects sharing one root."""

    def _race(self, *, sqlite):
        first, second = self._two_bridges(sqlite=sqlite)
        baseline = deepcopy(first.getState())
        snapshots = [self._ui_state(first), self._ui_state(second)]
        self.assertEqual(snapshots[0]["__localRevision"],
                         snapshots[1]["__localRevision"],
                         "The two concurrent writers must share one UI baseline")
        self.assertEqual(
            [{key: value for key, value in state.items() if not key.startswith("__")}
             for state in snapshots], [baseline, baseline],
            "The competing snapshots must be detached copies of identical state")

        # Each writer changes a DIFFERENT card and also claims the same shared
        # financial project field. Exactly one entire payload may commit.
        edits = (
            (FIRST_ID, "racing writer A", 991_007, 6_250_000),
            (SECOND_ID, "racing writer B", 882_009, 7_350_000),
        )
        for snapshot, (identifier, title, cost, project_price) in zip(snapshots, edits):
            card(snapshot, identifier)["title"] = title
            card(snapshot, identifier)["cost"] = cost
            project = next(item for item in snapshot["projects"] if item["id"] == "p-sample")
            project["price"] = project_price

        # All writers enter saveState only after the third-party test thread
        # releases this barrier. Avoid relying on sleeps, artificial delays or
        # patching the lock that the production code must exercise.
        start = Barrier(3, timeout=10)

        def save(index, bridge):
            start.wait()
            try:
                result = bridge.saveState(snapshots[index])
            except Exception as exc:
                return ("rejected", index, exc)
            return ("committed", index, result)

        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="madar-cas-race") as executor:
            future_a = executor.submit(save, 0, first)
            future_b = executor.submit(save, 1, second)
            start.wait()
            results = [future_a.result(timeout=20), future_b.result(timeout=20)]

        committed = [item for item in results if item[0] == "committed"]
        rejected = [item for item in results if item[0] == "rejected"]
        self.assertEqual(len(committed), 1,
                         f"P0 concurrent double-save or no-save: {results!r}")
        self.assertEqual(len(rejected), 1,
                         f"P0 concurrent writes must produce one conflict: {results!r}")
        self.assertIsInstance(rejected[0][2], (RuntimeError, ValueError),
                              f"Unexpected writer exception: {rejected[0][2]!r}")
        self.assertIn("CONFLICT", str(rejected[0][2]),
                      f"The rejected writer did not receive a CAS conflict: {results!r}")
        winner_index = committed[0][1]
        self.assertIn("localRevision", committed[0][2],
                      "Successful UI writer must get its next local revision")

        # Compare the complete canonical state to the winning writer's exact
        # payload, and check loser-specific financial changes did not leak.
        expected = native_app.normalize_state({
            key: deepcopy(value) for key, value in snapshots[winner_index].items()
            if not key.startswith("__")
        })
        fresh = native_app.Bridge()
        self._assert_safe_bridge(fresh)
        actual = fresh.getState()
        self.assertEqual(actual, expected,
                         "Concurrent stale writer clobbered or partially merged the winner")
        self.assertEqual(card(actual, edits[winner_index][0])["cost"],
                         edits[winner_index][2],
                         "The committed writer's financial card value was lost")
        loser_index = 1 - winner_index
        self.assertEqual(card(actual, edits[loser_index][0])["cost"],
                         card(baseline, edits[loser_index][0])["cost"],
                         "Rejected writer's financial card edit leaked onto disk")
        project = next(item for item in actual["projects"] if item["id"] == "p-sample")
        self.assertEqual(project["price"], edits[winner_index][3],
                         "Project price must belong exclusively to the committed writer")

        if sqlite:
            store = UnifiedAppStorage(first.unified_path)
            self.assertTrue(store.integrity_check())
            self.assertEqual(store.load().bundle["tasks"], actual)
        else:
            self.assertEqual(native_app.normalize_state(
                json.loads(first.path.read_text(encoding="utf-8"))), actual)

    def test_json_simultaneous_bridges_commit_exactly_once(self):
        self._race(sqlite=False)

    def test_sqlite_simultaneous_bridges_commit_exactly_once(self):
        self._race(sqlite=True)


class LocalCASControls(LocalCASFixture):
    def test_json_one_writer_can_save_and_reopen_without_losing_cost(self):
        self._one_writer_roundtrip(sqlite=False)

    def test_sqlite_one_writer_can_save_and_reopen_without_losing_cost(self):
        self._one_writer_roundtrip(sqlite=True)

    def test_json_backup_and_raw_read_exclude_ui_revision_metadata(self):
        ui_snapshot = self._ui_state(self.first)
        self.assertTrue(ui_snapshot["__localRevision"])
        plain = self.first.getState()
        self.assertNotIn("__localRevision", plain)
        archive = self.first.createLocalBackup()
        path = Path(archive["path"]).resolve()
        self.assertEqual(path.parent, self.root / "backups")
        backed_up = json.loads(path.read_text(encoding="utf-8"))
        self.assertNotIn("__localRevision", backed_up)
        self.assertNotIn("__remoteRevision", backed_up)
        self.assertEqual(backed_up, plain)

    def _one_writer_roundtrip(self, sqlite):
        first, second = self._two_bridges(sqlite=sqlite)
        before = self._ui_state(first)
        self.assertNotIn("__remoteRevision", before)
        card(before, FIRST_ID)["title"] = FIRST_TITLE
        card(before, FIRST_ID)["cost"] = FIRST_COST
        first.saveState(before)
        reopened = second.getState()
        self.assertEqual(card(reopened, FIRST_ID)["title"], FIRST_TITLE)
        self.assertEqual(card(reopened, FIRST_ID)["cost"], FIRST_COST)

    def test_underlying_sqlite_storage_cas_rejects_actual_stale_head(self):
        first, second = self._two_bridges(sqlite=True)
        store_a = UnifiedAppStorage(first.unified_path)
        store_b = UnifiedAppStorage(second.unified_path)
        baseline_a = store_a.load()
        baseline_b = store_b.load()
        self.assertEqual(baseline_a.revision, baseline_b.revision)
        next_bundle = deepcopy(baseline_a.bundle)
        card(next_bundle["tasks"], FIRST_ID)["title"] = FIRST_TITLE
        committed = store_a.commit(next_bundle,
                                   expected_revision=baseline_a.revision)
        stale_bundle = deepcopy(baseline_b.bundle)
        card(stale_bundle["tasks"], SECOND_ID)["title"] = SECOND_TITLE
        with self.assertRaisesRegex(RevisionConflict, "CONFLICT"):
            store_b.commit(stale_bundle, expected_revision=baseline_b.revision)
        persisted = store_a.load()
        self.assertEqual(persisted.revision, committed.revision)
        self.assertEqual(card(persisted.bundle["tasks"], FIRST_ID)["title"], FIRST_TITLE)


if __name__ == "__main__":
    unittest.main()
