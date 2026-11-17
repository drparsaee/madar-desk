"""Read-only E2 audit probes using only disposable, synthetic Windows profiles.

The tests deliberately contain negative security contracts. A failed test may
represent a genuine current-source defect; do NOT relax it to make CI green.
No real Taraz, financial data, installed services, or network is contacted.
"""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import native_app
from mtr_e2_send_journal import (
    assert_prepared_matches_if_present, prepare_manual_send,
)
from taraz_exchange import queue_saved_task


ROOT = Path(__file__).resolve().parents[1]
TASK = "synthetic-task-e2"
PROJECT = "synthetic-project-e2"
ACTOR = "client:synthetic-user"


def synthetic_state():
    return {"tasks": [{
        "id": TASK, "projectId": PROJECT, "title": "Synthetic first send",
        "checklist": [], "internalPassword": "SECRET_PASS_993",
        "customerPhone": "SECRET_PHONE_993", "apiToken": "SECRET_TOKEN_993",
    }]}


class JournalFaultTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="madar-e2-journal-fault-")
        self.addCleanup(temp.cleanup)
        self.profile = Path(temp.name)
        self.root = self.profile / "Madar-Taraz-Bridge"
        env = patch.dict(os.environ, {
            "LOCALAPPDATA": str(self.profile), "APPDATA": str(self.profile),
            "USERPROFILE": str(self.profile), "HOME": str(self.profile),
            "TEMP": str(self.profile), "TMP": str(self.profile),
        })
        env.start()
        self.addCleanup(env.stop)
        self.state = synthetic_state()

    def prepare(self, actor=ACTOR):
        return prepare_manual_send(self.state, TASK, actor_scope=actor)

    def paths(self):
        return list((self.root / "send-intents").glob("*.json"))

    def fake_native(self, *, mode="solo", user=None, connection=None):
        bridge = native_app.Bridge.__new__(native_app.Bridge)
        bridge._lock = threading.RLock()
        bridge.connection = connection or {"mode": mode}
        bridge.remote_user = user
        bridge.lan = None
        bridge.getState = lambda: deepcopy(self.state)
        return bridge

    def test_concurrent_prepare_is_single_durable_request_across_windows_processes(self):
        """Real Python child processes contend on the same Windows NTFS path."""
        if os.name != "nt":
            self.skipTest("Windows multi-process hard-link probe")
        release = self.profile / "release"
        script = (
            "import os, json, time, pathlib, sys\n"
            "from mtr_e2_send_journal import prepare_manual_send\n"
            "state={'tasks':[{'id':'synthetic-task-e2','projectId':'synthetic-project-e2',"
            "'title':'Synthetic first send','checklist':[]}]}\n"
            "pathlib.Path(os.environ['E2_READY']).write_text('ready')\n"
            "deadline=time.monotonic()+15\n"
            "while not pathlib.Path(os.environ['E2_RELEASE']).exists():\n"
            "  if time.monotonic()>=deadline: raise TimeoutError('barrier')\n"
            "  time.sleep(0.015)\n"
            "print(json.dumps(prepare_manual_send(state,'synthetic-task-e2',"
            "actor_scope='client:synthetic-user')),flush=True)\n"
        )
        children = []
        try:
            for n in range(4):
                marker = self.profile / ("ready-" + str(n))
                child = subprocess.Popen(
                    [sys.executable, "-B", "-c", script],
                    cwd=str(ROOT),
                    env=dict(os.environ, E2_READY=str(marker), E2_RELEASE=str(release)),
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, encoding="utf8", errors="replace",
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                children.append((child, marker))
            deadline = time.monotonic() + 14
            while (not all(marker.exists() for _, marker in children)
                   and time.monotonic() < deadline):
                if any(proc.poll() is not None for proc, _ in children):
                    break
                time.sleep(0.02)
            self.assertTrue(all(marker.exists() for _, marker in children),
                            "A child failed to reach the contention barrier")
            release.touch()
            results = []
            for child, _ in children:
                output, error = child.communicate(timeout=25)
                self.assertEqual(child.returncode, 0, error[-1000:])
                results.append(json.loads(output))
            self.assertEqual(len({r["id"] for r in results}), 1)
            self.assertEqual([r["reused"] for r in results].count(False), 1)
            self.assertEqual(len(self.paths()), 1)
            self.assertEqual(list((self.root / "send-intents").glob("*.tmp")), [])
            self.assertFalse((self.root / "pending").exists())
        finally:
            release.touch()
            for child, _ in children:
                if child.poll() is None:
                    child.kill()
                child.communicate(timeout=10)

    def test_corrupt_journal_rejects_duplicates_invalid_utf8_truncation_and_oversize(self):
        for index, raw in enumerate((
            b'{"schemaVersion":1,"schemaVersion":1}',
            b"\xff\xfe\xff",
            b'{"schemaVersion":1}',
            b"x" * 4097,
            b"",
        )):
            with self.subTest(index=index):
                with tempfile.TemporaryDirectory(prefix="mtr-e2-corrupt-") as scratch:
                    with patch.dict(os.environ, {"LOCALAPPDATA": scratch}):
                        first = self.prepare()
                        file = next((Path(scratch) / "Madar-Taraz-Bridge"
                                     / "send-intents").glob("*.json"))
                        file.write_bytes(raw)
                        with self.assertRaises((
                            ValueError, PermissionError, UnicodeDecodeError,
                            json.JSONDecodeError,
                        )):
                            self.prepare()
                        self.assertEqual(file.read_bytes(), raw)
                        self.assertFalse((Path(scratch) / "Madar-Taraz-Bridge"
                                          / "pending").exists())
                        self.assertEqual(len(list(file.parent.glob("*.json"))), 1)
                        self.assertNotEqual(first["id"], "0" * 32)

    def test_symlinked_journal_and_directory_are_denied(self):
        with tempfile.TemporaryDirectory(prefix="mtr-e2-private-") as outside:
            self.root.mkdir()
            folder = self.root / "send-intents"
            try:
                folder.symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError) as error:
                self.skipTest("Windows symlink permission unavailable: " + str(error))
            with self.assertRaises(PermissionError):
                self.prepare()
            self.assertFalse(list(Path(outside).iterdir()))

    def test_hardlinked_existing_intent_rejects_reparse_like_aliasing(self):
        self.prepare()
        file = self.paths()[0]
        twin = self.profile / "hardlink-alias.json"
        os.link(file, twin)
        self.assertGreaterEqual(file.stat().st_nlink, 2)
        with self.assertRaises(PermissionError):
            self.prepare()
        self.assertFalse((self.root / "pending").exists())

    def test_interrupted_link_before_publish_leaves_no_json_or_tmp(self):
        with patch("mtr_e2_send_journal.os.link",
                   side_effect=OSError("synthetic link not performed")):
            with self.assertRaisesRegex(OSError, "synthetic link"):
                self.prepare()
        self.assertEqual(self.paths(), [])
        self.assertEqual(list((self.root / "send-intents").glob("*.tmp")), [])
        self.assertFalse((self.root / "pending").exists())
        self.assertFalse(self.prepare()["reused"])

    def test_lost_reply_after_atomic_link_reuses_original_intent_id(self):
        original_link = os.link

        def publish_then_fail(src, dest):
            original_link(src, dest)
            raise OSError("synthetic process crash after commit")

        with patch("mtr_e2_send_journal.os.link", side_effect=publish_then_fail):
            with self.assertRaisesRegex(OSError, "synthetic process crash"):
                self.prepare()
        first = json.loads(self.paths()[0].read_text(encoding="utf8"))["requestId"]
        repeated = self.prepare()
        self.assertEqual(repeated["id"], first)
        self.assertTrue(repeated["reused"])
        self.assertEqual(len(self.paths()), 1)
        self.assertEqual(list((self.root / "send-intents").glob("*.tmp")), [])

    def test_scope_separates_actors_hosts_and_tls_fingerprints(self):
        a = self.prepare("client:one")
        b = self.prepare("client:two")
        self.assertNotEqual(a["id"], b["id"])
        self.assertEqual(len(self.paths()), 2)
        scopes = []
        for account, url, fingerprint in (
            ("member", "https://host-a:48370", "aa" * 32),
            ("member", "https://host-b:48370", "aa" * 32),
            ("member", "https://host-a:48370", "bb" * 32),
            ("other", "https://host-a:48370", "aa" * 32),
        ):
            bridge = self.fake_native(
                mode="client", user={"username": account, "role": "editor"},
                connection={"mode": "client", "url": url, "fingerprint": fingerprint},
            )
            scopes.append(bridge._taraz_actor_scope())
        # Current code intentionally uses a pinned certificate as peer identity,
        # so DNS/IP changes under that *same pin* preserve the journal scope.
        self.assertEqual(scopes[0], scopes[1])
        self.assertEqual(len({scopes[0], scopes[2], scopes[3]}), 3)
        # An unverified URL/IP is never a durable actor identity for finance.
        for url in ("https://host-a:48370", "https://host-b:48370", "http://host-a:48370"):
            bridge = self.fake_native(
                mode="client", user={"username": "member", "role": "editor"},
                connection={"mode": "client", "url": url, "fingerprint": ""},
            )
            with self.subTest(url=url), self.assertRaises(PermissionError):
                bridge._taraz_actor_scope()

    def test_unknown_identity_or_viewer_cannot_prepare_or_queue(self):
        for bad_user in (None, {"username": "u", "role": "viewer"},
                         {"username": "", "role": "editor"},
                         {"username": "u", "role": "owner"}):
            bridge = self.fake_native(
                mode="client", user=bad_user,
                connection={"mode": "client", "url": "https://host:48370",
                            "fingerprint": "ff"},
            )
            with self.subTest(user=bad_user), self.assertRaises(PermissionError):
                bridge.tarazIntegrationPrepare(TASK)
            with self.subTest(user=bad_user), self.assertRaises(PermissionError):
                bridge.tarazIntegrationQueue(TASK, None, "a" * 32)
        self.assertEqual(self.paths(), [])

    def test_client_project_acl_and_offline_preflight_denies_prepare_and_queue(self):
        bridge = self.fake_native(
            mode="client", user={
                "username": "user", "role": "editor",
                "projects": ["different-project"],
            },
            connection={"mode": "client", "url": "https://host:48370",
                        "fingerprint": "ff"},
        )
        with self.assertRaises(PermissionError):
            bridge.tarazIntegrationPrepare(TASK)
        with self.assertRaises(PermissionError):
            bridge.tarazIntegrationQueue(TASK, None, "a" * 32)
        bridge.connection["mode"] = "solo"
        bridge.getState = lambda: {"__offline": True, **self.state}
        with self.assertRaises(RuntimeError):
            bridge.tarazIntegrationPrepare(TASK)
        with self.assertRaises(RuntimeError):
            bridge.tarazIntegrationQueue(TASK, None, "a" * 32)
        self.assertFalse((self.root / "pending").exists())

    def test_stale_saved_task_rejects_queue_and_does_not_emit_file(self):
        bridge = self.fake_native()
        prepared = bridge.tarazIntegrationPrepare(TASK)
        self.state["tasks"][0]["title"] = "Different saved snapshot"
        with self.assertRaises(PermissionError):
            bridge.tarazIntegrationQueue(TASK, None, prepared["id"])
        with self.assertRaises(ValueError):
            bridge.tarazIntegrationPrepare(TASK)
        self.assertFalse((self.root / "pending").exists())

    def test_raw_unsaved_ui_state_is_not_used_by_native_prepare(self):
        stored = deepcopy(self.state)
        unsaved = deepcopy(stored)
        unsaved["tasks"][0]["title"] = "Unsaved draft with different content"
        bridge = self.fake_native()
        result = bridge.tarazIntegrationPrepare(TASK)
        self.assertTrue(result["prepared"])
        # Native API gets the persisted snapshot; the App's dirty.current UI
        # gate must block sending while the user has unpersisted changes.
        self.assertNotEqual(stored["tasks"][0]["title"], unsaved["tasks"][0]["title"])
        self.assertFalse((self.root / "pending").exists())

    def test_journal_never_embeds_unselected_password_phone_or_api_token(self):
        state_before = deepcopy(self.state)
        self.prepare()
        blob = self.paths()[0].read_text(encoding="utf8")
        for secret in ("SECRET_PASS_993", "SECRET_PHONE_993", "SECRET_TOKEN_993",
                       "Synthetic first send"):
            self.assertNotIn(secret, blob)
        self.assertEqual(self.state, state_before)

    def test_ui_guard_checks_unsaved_state_before_first_prepare(self):
        app = (ROOT / "src" / "App.jsx").read_text(encoding="utf8")
        send_start = app.index("const sendToTaraz=async(")
        send_end = app.index("  if(!data)return", send_start)
        body = app[send_start:send_end]
        self.assertIn("dirty.current||saving.current||blocked.current", body)
        self.assertLess(
            body.index("dirty.current||saving.current||blocked.current"),
            body.index("api.tarazIntegrationPrepare(taskId)"),
        )

    def test_native_first_send_ui_bridge_must_expose_prepare(self):
        # Explicit security/availability regression contract. On the current
        # source this fails: JSX calls a wrapper the JS bridge omits.
        script = native_app.JS_BRIDGE.split(".map(key")[0]
        exported = set(re.findall(r"'([A-Za-z_]\w*)'", script))
        app = (ROOT / "src" / "App.jsx").read_text(encoding="utf8")
        self.assertIn("api.tarazIntegrationPrepare(taskId)", app)
        self.assertIn("tarazIntegrationQueue", exported)
        self.assertIn("tarazIntegrationPrepare", exported,
                      "App first send cannot invoke a non-exported native wrapper")

    def test_direct_bridge_queue_without_preparation_must_fail_closed(self):
        # Explicit security regression contract: public pywebview Bridge
        # currently allows old requestId=None path to publish without journal.
        bridge = self.fake_native()
        with self.assertRaises((PermissionError, RuntimeError, ValueError)):
            bridge.tarazIntegrationQueue(TASK)
        self.assertFalse((self.root / "pending").exists())

    def test_arbitrary_explicit_id_without_preparation_must_fail_closed(self):
        # assert_prepared_matches_if_present returns hasPreparedIntent=False,
        # but caller ignores it and publishes a caller-selected request ID.
        bridge = self.fake_native()
        with self.assertRaises((PermissionError, RuntimeError, ValueError)):
            bridge.tarazIntegrationQueue(TASK, None, "e" * 32)
        self.assertFalse((self.root / "pending").exists())

    def test_changing_authenticated_actor_after_prepare_must_not_publish_foreign_id(self):
        identity = {"mode": "client", "url": "https://test-host:48370",
                    "fingerprint": "ab" * 32}
        first = self.fake_native(
            mode="client", user={"username": "alice", "role": "editor",
                                  "projects": [PROJECT]},
            connection=dict(identity),
        )
        intent = first.tarazIntegrationPrepare(TASK)
        other = self.fake_native(
            mode="client", user={"username": "bob", "role": "editor",
                                  "projects": [PROJECT]},
            connection=dict(identity),
        )
        self.assertNotEqual(first._taraz_actor_scope(), other._taraz_actor_scope())
        with self.assertRaises((PermissionError, RuntimeError, ValueError)):
            other.tarazIntegrationQueue(TASK, None, intent["id"])
        self.assertFalse((self.root / "pending").exists())


if __name__ == "__main__":
    unittest.main()
