"""Isolated acceptance tests for the host-only 30-second backup scheduler.

Only disposable directories and synthetic bridges are used. No APPDATA, real
LAN host, installed EXE, real accounting data or Windows registry is accessed.
"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from host_backup_scheduler import (
    HostBackupError, HostBackupScheduler, INDEX_NAME, INTERVAL_SECONDS,
)


class SyntheticBridge:
    def __init__(self, root):
        self.path = root / "tasks.json"
        self.backups_dir = root / "backups"
        self.connection = {"mode": "solo"}
        self._lock = threading.RLock()
        self._unified_store = None
        self.writes = 0
        self.fail_backup = False
        self.incomplete = False
        self.counter = 0
        self.replace_state({"tasks": [{"id": "task-1", "title": "original"}]})

    def replace_state(self, state):
        # Simulate an already committed, validated native host state.
        self.path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    def _load(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def createLocalBackup(self):
        if self.connection["mode"] == "client":
            raise PermissionError("Host only")
        with self._lock:
            if self.fail_backup:
                raise OSError("Synthetic disk full")
            self.backups_dir.mkdir(exist_ok=True)
            self.counter += 1
            name = f"madar-20261028-130000-{self.counter:06d}.json"
            target = self.backups_dir / name
            target.write_text(json.dumps(self._load(), ensure_ascii=False),
                              encoding="utf-8")
            self.writes += 1
            return {
                "name": name, "path": str(target),
                "complete": self.incomplete, "scope": "task-state-only",
                "omitted": [
                    "finance", "collaboration", "attachment-binaries",
                    "planner-local-storage", "lan-accounts", "login-credentials",
                ],
            }


class SyntheticUnifiedStore:
    def __init__(self, path):
        self.path = path
        with closing(sqlite3.connect(path)) as conn:
            with conn:
                conn.execute("CREATE TABLE app_head (id INTEGER PRIMARY KEY, revision INTEGER)")
                conn.execute("CREATE TABLE app_revisions (revision INTEGER PRIMARY KEY, digest TEXT)")
                conn.execute("INSERT INTO app_head VALUES (1, 1)")
                conn.execute("INSERT INTO app_revisions VALUES (1, ?)", ("1" * 64,))

    def load(self):
        with closing(sqlite3.connect(self.path)) as conn:
            row = conn.execute(
                "SELECT digest FROM app_revisions WHERE revision="
                "(SELECT revision FROM app_head WHERE id=1)"
            ).fetchone()
        return SimpleNamespace(sha256=row[0])

    def change_revision(self, digest):
        with closing(sqlite3.connect(self.path)) as conn:
            with conn:
                rev = conn.execute("SELECT revision FROM app_head").fetchone()[0] + 1
                conn.execute("INSERT INTO app_revisions VALUES (?, ?)", (rev, digest))
                conn.execute("UPDATE app_head SET revision=?", (rev,))


class SyntheticSqliteBridge(SyntheticBridge):
    def __init__(self, root):
        super().__init__(root)
        self._unified_store = SyntheticUnifiedStore(root / "madar-unified.sqlite3")

    def createLocalBackup(self):
        if self.fail_backup:
            raise OSError("Synthetic SQLite disk full")
        with self._lock:
            self.backups_dir.mkdir(exist_ok=True)
            self.counter += 1
            name = f"madar-unified-20261028-130000-{self.counter:06d}.sqlite3"
            path = self.backups_dir / name
            with closing(sqlite3.connect(self._unified_store.path)) as conn:
                with closing(sqlite3.connect(path)) as target:
                    conn.backup(target)
            self.writes += 1
            return {
                "name": name, "path": str(path), "scope": "sqlite-domains-only",
                "complete": False,
                "omitted": [
                    "attachment-binaries", "planner-local-storage",
                    "lan-accounts", "login-credentials",
                ],
            }


class HostBackupSchedulerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="madar-host-periodic-synthetic-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.bridge = SyntheticBridge(self.root)
        self.scheduler = HostBackupScheduler(self.bridge, max_backups=3)

    def index(self):
        return json.loads(
            (self.bridge.backups_dir / INDEX_NAME).read_text(encoding="utf-8")
        )["entries"]

    def change(self, title):
        self.bridge.replace_state({"tasks": [{"id": "task-1", "title": title}]})

    def test_default_cadence_and_no_work_before_start(self):
        self.assertEqual(INTERVAL_SECONDS, 30)
        self.assertEqual(HostBackupScheduler(self.bridge).interval_seconds, 30)
        self.assertFalse(self.bridge.backups_dir.exists())
        self.assertEqual(self.bridge.writes, 0)
        self.assertFalse(self.scheduler.status()["running"])

    def test_first_snapshot_and_unchanged_revision_deduplicate_after_restart(self):
        self.assertTrue(self.scheduler.run_once())
        first = self.index()[0]
        self.assertEqual(first["scope"], "task-state-only")
        self.assertTrue((self.bridge.backups_dir / first["name"]).exists())
        self.assertFalse(self.scheduler.run_once())
        self.assertFalse(HostBackupScheduler(self.bridge).run_once())
        self.assertEqual(self.bridge.writes, 1)
        status = self.scheduler.status()
        self.assertEqual(status["backupCount"], 1)
        self.assertIsNone(status["lastError"])
        self.assertFalse(status["complete"])

    def test_every_changed_revision_creates_one_backup_with_exact_content(self):
        self.assertTrue(self.scheduler.run_once())
        for number in range(1, 3):
            title = f"new-{number}"
            self.change(title)
            self.assertTrue(self.scheduler.run_once())
            saved = self.index()[-1]["name"]
            self.assertEqual(json.loads(
                (self.bridge.backups_dir / saved).read_text(encoding="utf-8")
            )["tasks"][0]["title"], title)
            self.assertFalse(self.scheduler.run_once())
        self.assertEqual(self.bridge.writes, 3)
        self.assertEqual(len(self.index()), 3)

    def test_retention_only_touches_indexed_periodic_files(self):
        folder = self.bridge.backups_dir
        folder.mkdir()
        manual = folder / "madar-20261028-140000-101001.json"
        manual.write_text("manual", encoding="utf-8")
        daily = folder / "auto-20261028-140000-101002.json"
        daily.write_text("daily", encoding="utf-8")
        unexpected = folder / "do-not-delete.json"
        unexpected.write_text("private", encoding="utf-8")
        for n in range(5):
            self.change(str(n))
            self.assertTrue(self.scheduler.run_once())
        self.assertEqual(len(self.index()), 3)
        self.assertEqual(len(list(folder.glob("madar-20261028-130000-*.json"))), 3)
        self.assertEqual(manual.read_text(), "manual")
        self.assertEqual(daily.read_text(), "daily")
        self.assertEqual(unexpected.read_text(), "private")

    def test_client_rejected_before_creating_folder_or_thread(self):
        self.bridge.connection = {"mode": "client"}
        with self.assertRaises(PermissionError):
            self.scheduler.start()
        self.assertFalse(self.scheduler.status()["running"])
        self.assertFalse(self.bridge.backups_dir.exists())
        self.assertEqual(self.bridge.writes, 0)

    def test_folder_and_index_problems_fail_closed_without_pruning(self):
        folder = self.bridge.backups_dir
        folder.write_text("not a directory", encoding="utf-8")
        with self.assertRaisesRegex(HostBackupError, "directory"):
            self.scheduler.run_once()
        self.assertEqual(self.bridge.writes, 0)
        self.assertTrue(self.scheduler.status()["lastError"])
        folder.unlink()
        self.assertTrue(self.scheduler.run_once())
        original = self.index()[0]["name"]
        (folder / INDEX_NAME).write_text('{"schema":7}', encoding="utf-8")
        self.change("changed")
        with self.assertRaisesRegex(HostBackupError, "index"):
            self.scheduler.run_once()
        self.assertEqual(self.bridge.writes, 1)
        self.assertTrue((folder / original).exists())

    def test_indexed_backup_tampering_is_detected_before_duplicate_or_rotation(self):
        self.assertTrue(self.scheduler.run_once())
        original = self.index()[0]["name"]
        file = self.bridge.backups_dir / original
        file.write_text("corrupted", encoding="utf-8")
        with self.assertRaisesRegex(HostBackupError, "changed on disk"):
            self.scheduler.run_once()
        self.assertEqual(self.bridge.writes, 1)
        self.assertEqual(len(self.index()), 1)
        self.assertTrue(file.exists())

    def test_backup_directory_symbolic_link_is_refused_when_supported(self):
        outside = self.root / "outside"
        outside.mkdir()
        try:
            self.bridge.backups_dir.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Synthetic Windows account cannot create symlinks")
        with self.assertRaisesRegex(HostBackupError, "directory"):
            self.scheduler.run_once()
        self.assertEqual(self.bridge.writes, 0)
        self.assertEqual(list(outside.iterdir()), [])

    def test_corrupt_or_unsupported_backup_does_not_retire_old_backups(self):
        self.assertTrue(self.scheduler.run_once())
        former = self.index()[0]["name"]
        self.bridge.incomplete = True
        self.change("should-fail")
        with self.assertRaisesRegex(HostBackupError, "partial"):
            self.scheduler.run_once()
        self.assertEqual(len(self.index()), 1)
        self.assertTrue((self.bridge.backups_dir / former).exists())
        self.assertEqual(self.scheduler.status()["failureCount"], 1)
        self.bridge.incomplete = False
        self.assertTrue(self.scheduler.run_once())
        self.assertIsNone(self.scheduler.status()["lastError"])

    def test_failed_disk_write_retains_previous_and_reports_error(self):
        self.scheduler.run_once()
        previous = self.index()[0]["name"]
        self.change("later")
        self.bridge.fail_backup = True
        with self.assertRaisesRegex(OSError, "disk full"):
            self.scheduler.run_once()
        self.assertEqual(len(self.index()), 1)
        self.assertTrue((self.bridge.backups_dir / previous).exists())
        self.assertIn("disk full", self.scheduler.status()["lastError"])

    def test_managed_backup_missing_recreates_snapshot_even_without_new_revision(self):
        self.scheduler.run_once()
        (self.bridge.backups_dir / self.index()[0]["name"]).unlink()
        self.assertTrue(self.scheduler.run_once())
        self.assertEqual(self.bridge.writes, 2)

    def test_published_backup_is_kept_if_index_write_fails(self):
        with patch.object(HostBackupScheduler, "_publish_index", side_effect=OSError("index full")):
            with self.assertRaisesRegex(OSError, "index full"):
                self.scheduler.run_once()
        self.assertEqual(self.bridge.writes, 1)
        saved = self.bridge.backups_dir / "madar-20261028-130000-000001.json"
        self.assertTrue(saved.exists())
        self.assertFalse((self.bridge.backups_dir / INDEX_NAME).exists())
        self.assertTrue(self.scheduler.run_once())
        self.assertEqual(len(self.index()), 1)
        self.assertTrue(saved.exists())  # The orphan is not mistaken for an indexed backup.

    def test_rotation_index_failure_keeps_retired_backup_bytes(self):
        # A full index can be published before a second, pruned index fails.
        # The failure must not delete a valid old snapshot first.
        scheduler = HostBackupScheduler(self.bridge, max_backups=1)
        self.assertTrue(scheduler.run_once())
        original = self.bridge.backups_dir / self.index()[0]["name"]
        original_bytes = original.read_bytes()
        self.change("new revision")
        publish = HostBackupScheduler._publish_index
        attempts = 0

        def fail_pruned_index(folder, entries):
            nonlocal attempts
            attempts += 1
            if attempts == 2:
                raise OSError("synthetic index fsync failure")
            return publish(folder, entries)

        with patch.object(HostBackupScheduler, "_publish_index",
                          side_effect=fail_pruned_index):
            with self.assertRaisesRegex(OSError, "index fsync failure"):
                scheduler.run_once()
        self.assertEqual(attempts, 2)
        self.assertEqual(original.read_bytes(), original_bytes)
        self.assertEqual(len(self.index()), 2)

    def test_sqlite_revision_changes_and_published_backup_integrity(self):
        self.bridge = SyntheticSqliteBridge(self.root)
        scheduler = HostBackupScheduler(self.bridge, max_backups=2)
        self.assertTrue(scheduler.run_once())
        self.assertFalse(scheduler.run_once())
        self.bridge._unified_store.change_revision("2" * 64)
        self.assertTrue(scheduler.run_once())
        self.bridge._unified_store.change_revision("3" * 64)
        self.assertTrue(scheduler.run_once())
        entries = json.loads((self.bridge.backups_dir / INDEX_NAME).read_text())["entries"]
        self.assertEqual(len(entries), 2)
        self.assertTrue(all(item["scope"] == "sqlite-domains-only" for item in entries))
        for entry in entries:
            with closing(sqlite3.connect(self.bridge.backups_dir / entry["name"])) as conn:
                self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone(), ("ok",))

    def test_background_start_stop_and_host_transition(self):
        scheduler = HostBackupScheduler(self.bridge, interval_seconds=0.04)
        self.addCleanup(scheduler.stop)
        self.assertTrue(scheduler.start()["running"])
        self.assertEqual(self.bridge.writes, 1)
        self.change("changed")
        deadline = time.monotonic() + 2
        while self.bridge.writes < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(self.bridge.writes, 2)
        self.bridge.connection = {"mode": "client"}
        deadline = time.monotonic() + 2
        while scheduler.status()["running"] and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertFalse(scheduler.status()["running"])
        self.assertIn("host-only", scheduler.status()["lastError"])
        scheduler.stop()
        self.assertEqual(self.bridge.writes, 2)

    def test_cross_scheduler_calls_do_not_duplicate_one_revision(self):
        other = HostBackupScheduler(self.bridge)
        gate = threading.Barrier(3)
        results = []
        def run(scheduler):
            gate.wait(timeout=2)
            results.append(scheduler.run_once())
        a = threading.Thread(target=run, args=(self.scheduler,))
        b = threading.Thread(target=run, args=(other,))
        a.start()
        b.start()
        gate.wait(timeout=2)
        a.join(timeout=2)
        b.join(timeout=2)
        self.assertFalse(a.is_alive() or b.is_alive())
        self.assertCountEqual(results, [True, False])
        self.assertEqual(self.bridge.writes, 1)


if __name__ == "__main__":
    unittest.main()
