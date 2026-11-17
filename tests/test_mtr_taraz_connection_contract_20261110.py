"""P0 Madar/Taraz manual proposal contract against real source methods.

Only synthetic in-memory tasks and disposable LOCALAPPDATA are used. Bridge
methods are invoked directly; no application profile, network, installer,
actual Taraz book, or financial API is opened. Client identity/state inputs
are deliberately simulated, so this is not a host authentication test.
"""

import copy
import importlib.util
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import unittest
from unittest.mock import patch

import native_app


TARAZ_SOURCE = (
    Path(__file__).resolve().parents[3]
    / "000- Taraz" / "taraz-mtr-e2-isolated-20261109" / "taraz_integration.py"
)


class TarazConnectionContract(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="mtr-p0-local-contract-")
        self.addCleanup(directory.cleanup)
        self.local = Path(directory.name)
        environment = patch.dict(os.environ, {
            "LOCALAPPDATA": str(self.local),
            "APPDATA": str(self.local),
            "USERPROFILE": str(self.local),
            "HOME": str(self.local),
            "TEMP": str(self.local),
            "TMP": str(self.local),
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.inbox = self.local / "Madar-Taraz-Bridge"
        self.state = {"tasks": [
            {"id": "task-a", "projectId": "project-a", "title": "Synthetic print request",
             "customerPrivate": "must-never-be-shared", "checklist": []},
            {"id": "task-b", "projectId": "project-b", "title": "Synthetic box request",
             "checklist": []},
        ]}
        # Construct only the attributes used by the actual Bridge methods.
        # Bridge.__init__ may load a running profile or start a LAN service.
        self.bridge = object.__new__(native_app.Bridge)
        self.bridge._lock = threading.RLock()
        self.bridge.connection = {"mode": "solo"}
        self.bridge.lan = None
        self.bridge.remote_user = None
        self.bridge.getState = lambda: copy.deepcopy(self.state)

    def pending(self):
        folder = self.inbox / "pending"
        return list(folder.glob("*.json")) if folder.is_dir() else []

    def client(self, role, projects, username="synthetic-editor"):
        self.bridge.connection = {
            "mode": "client",
            "url": "https://synthetic.invalid:48370",
            "fingerprint": "a" * 64,
        }
        self.bridge.remote_user = {
            "role": role, "projects": projects, "username": username,
        }

    @staticmethod
    def detached_taraz():
        if not TARAZ_SOURCE.is_file() or TARAZ_SOURCE.is_symlink():
            raise AssertionError("Isolated Taraz source unavailable; cannot claim cross-app QA")
        spec = importlib.util.spec_from_file_location(
            "mtr_p0_taraz_contract_source", TARAZ_SOURCE
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_manual_prepare_queue_replay_and_scoped_history(self):
        status = self.bridge.tarazIntegrationStatus()
        self.assertIs(status["supported"], True)
        self.assertIs(status["postingEnabled"], False)
        self.assertEqual(status["pending"], 0)
        self.assertEqual(self.bridge.tarazIntegrationHistory("task-a", False)["state"],
                         "disabled")

        prepared = self.bridge.tarazIntegrationPrepare("task-a")
        self.assertIs(prepared["prepared"], True)
        self.assertIs(prepared["reused"], False)
        self.assertIs(prepared["postingPerformed"], False)
        self.assertRegex(prepared["id"], r"^[0-9a-f]{32}$")
        self.assertEqual(self.pending(), [], "prepare must not publish")
        repeated = self.bridge.tarazIntegrationPrepare("task-a")
        self.assertEqual(repeated["id"], prepared["id"])
        self.assertIs(repeated["reused"], True)

        queued = self.bridge.tarazIntegrationQueue("task-a", None, prepared["id"])
        self.assertEqual(queued["id"], prepared["id"])
        self.assertIs(queued["queued"], True)
        self.assertIs(queued["replayed"], False)
        self.assertIs(queued["postingPerformed"], False)
        self.assertEqual(len(self.pending()), 1)
        payload = json.loads(self.pending()[0].read_text(encoding="utf-8"))
        self.assertEqual(
            set(payload),
            {"schema", "source", "id", "taskId", "projectId", "title", "createdUtc"},
        )
        self.assertEqual((payload["source"], payload["projectId"]),
                         ("madar", "project-a"))
        self.assertNotIn("must-never-be-shared", self.pending()[0].read_text("utf-8"))

        replay = self.bridge.tarazIntegrationQueue("task-a", None, prepared["id"])
        self.assertIs(replay["queued"], False)
        self.assertIs(replay["replayed"], True)
        self.assertEqual(replay["observedLocation"], "pending")
        self.assertEqual(len(self.pending()), 1)
        history = self.bridge.tarazIntegrationHistory("task-a", True)
        self.assertIs(history["supported"], True)
        self.assertIs(history["peerVerified"], False)
        self.assertIs(history["postingEnabled"], False)
        self.assertEqual([(item["id"], item["state"]) for item in history["items"]],
                         [(prepared["id"], "pending")])
        self.assertEqual(self.bridge.tarazIntegrationHistory("task-b", True)["items"], [])

    def test_real_detached_taraz_manual_review_and_rejection_roundtrip(self):
        taraz = self.detached_taraz()
        queued = {}
        for task in ("task-a", "task-b"):
            identifier = self.bridge.tarazIntegrationPrepare(task)["id"]
            self.assertIs(self.bridge.tarazIntegrationQueue(task, None, identifier)
                          ["postingPerformed"], False)
            queued[task] = identifier
        self.assertEqual(
            {item["id"] for item in taraz.list_requests(self.inbox)["requests"]},
            set(queued.values()),
        )
        for task, decision in (("task-a", "reviewed"), ("task-b", "rejected")):
            response = taraz.review_request(self.inbox, queued[task], decision)
            self.assertEqual(response["state"], decision)
            self.assertIs(response["financialEventCreated"], False)
            observed = self.bridge.tarazIntegrationHistory(task, True)
            self.assertEqual([(item["id"], item["state"]) for item in observed["items"]],
                             [(queued[task], decision)])
            self.assertIs(observed["peerVerified"], False)
            self.assertIs(observed["items"][0]["financialEventCreated"], False)
            replay = self.bridge.tarazIntegrationQueue(task, None, queued[task])
            self.assertIs(replay["replayed"], True)
            self.assertEqual(replay["observedLocation"], "reviewed")
            self.assertIs(replay["postingPerformed"], False)
        self.assertEqual(taraz.list_requests(self.inbox)["requests"], [])
        self.assertEqual(self.pending(), [])

    def test_no_unprepared_first_send_and_fail_closed_on_stale_task(self):
        with self.assertRaises(PermissionError):
            self.bridge.tarazIntegrationQueue("task-a")
        with self.assertRaises(PermissionError):
            self.bridge.tarazIntegrationQueue("task-a", None, "f" * 32)
        self.assertEqual(self.pending(), [])
        prepared = self.bridge.tarazIntegrationPrepare("task-a")
        self.state["tasks"][0]["title"] = "Changed after preparation"
        with self.assertRaises(PermissionError):
            self.bridge.tarazIntegrationQueue("task-a", None, prepared["id"])
        with self.assertRaises(ValueError):
            self.bridge.tarazIntegrationPrepare("task-a")
        self.assertEqual(self.pending(), [])
        self.state["tasks"][0]["title"] = "Synthetic print request"
        self.assertEqual(self.bridge.tarazIntegrationPrepare("task-a")["id"],
                         prepared["id"])
        self.bridge.tarazIntegrationQueue("task-a", None, prepared["id"])
        prior = self.pending()[0].read_bytes()
        self.state["tasks"][0]["title"] = "Stale after send"
        with self.assertRaises(PermissionError):
            self.bridge.tarazIntegrationQueue("task-a", None, prepared["id"])
        self.assertEqual(self.pending()[0].read_bytes(), prior)

    def test_duplicate_id_conflict_and_corrupt_receipt_are_never_approval(self):
        identifier = self.bridge.tarazIntegrationPrepare("task-a")["id"]
        self.bridge.tarazIntegrationQueue("task-a", None, identifier)
        source = self.pending()[0]
        reviewed = self.inbox / "reviewed"
        reviewed.mkdir(exist_ok=True)
        (reviewed / source.name).write_bytes(source.read_bytes())
        observed = self.bridge.tarazIntegrationHistory("task-a", True)
        self.assertEqual(observed["items"][0]["state"], "unknown")
        with self.assertRaises(RuntimeError):
            self.bridge.tarazIntegrationQueue("task-a", None, identifier)
        self.assertEqual(len(self.pending()), 1, "conflict must not republish")

        source.unlink()
        forged = {
            "schema": 1, "id": identifier, "source": "taraz",
            "state": "reviewed", "reviewedUtc": "2026-11-10T00:00:00+00:00",
            "taskId": "task-a", "financialEventCreated": True,
        }
        (reviewed / (identifier + ".review.json")).write_text(
            json.dumps(forged), encoding="utf-8"
        )
        history = self.bridge.tarazIntegrationHistory("task-a", True)
        self.assertEqual(history["items"][0]["state"], "unknown")
        self.assertIs(history["items"][0]["financialEventCreated"], False)
        self.assertIs(history["peerVerified"], False)

    def test_client_role_project_duplicate_task_and_offline_guards(self):
        self.client("viewer", ["project-a"])
        with self.assertRaises(PermissionError):
            self.bridge.tarazIntegrationPrepare("task-a")
        with self.assertRaises(PermissionError):
            self.bridge.tarazIntegrationQueue("task-a", None, "a" * 32)
        with self.assertRaises(PermissionError):
            self.bridge.tarazIntegrationHistory("task-a", True)

        self.client("editor", ["project-b"])
        for action in (
            lambda: self.bridge.tarazIntegrationPrepare("task-a"),
            lambda: self.bridge.tarazIntegrationQueue("task-a", None, "a" * 32),
            lambda: self.bridge.tarazIntegrationHistory("task-a", True),
        ):
            with self.subTest(action=action), self.assertRaises(PermissionError):
                action()
        self.assertEqual(self.pending(), [])
        self.client("editor", ["project-a"])
        prepared = self.bridge.tarazIntegrationPrepare("task-a")
        self.client("viewer", ["project-a"])
        with self.assertRaises(PermissionError):
            self.bridge.tarazIntegrationQueue("task-a", None, prepared["id"])
        self.assertEqual(self.pending(), [])
        self.client("editor", ["project-a"])
        self.assertIs(self.bridge.tarazIntegrationQueue("task-a", None, prepared["id"])
                      ["queued"], True)
        self.assertEqual(len(self.pending()), 1)

        self.state["tasks"].append(copy.deepcopy(self.state["tasks"][0]))
        for action in (
            lambda: self.bridge.tarazIntegrationPrepare("task-a"),
            lambda: self.bridge.tarazIntegrationQueue("task-a", None, prepared["id"]),
            lambda: self.bridge.tarazIntegrationHistory("task-a", True),
        ):
            with self.subTest(action=action), self.assertRaises(PermissionError):
                action()
        self.state["tasks"].pop()
        self.state["__offline"] = True
        for action in (
            lambda: self.bridge.tarazIntegrationPrepare("task-a"),
            lambda: self.bridge.tarazIntegrationQueue("task-a", None, prepared["id"]),
            lambda: self.bridge.tarazIntegrationHistory("task-a", True),
        ):
            with self.subTest(action=action), self.assertRaises(RuntimeError):
                action()
        self.assertEqual(len(self.pending()), 1)

    def test_client_actor_scope_denies_unpinned_and_http_hosts(self):
        for change in (
            {"fingerprint": ""},
            {"fingerprint": "not-a-sha256"},
            {"url": "http://synthetic.invalid:48370"},
            {"url": "https://synthetic.invalid:48370/path"},
        ):
            with self.subTest(change=change):
                self.client("editor", ["project-a"])
                self.bridge.connection.update(change)
                with self.assertRaises(PermissionError):
                    self.bridge.tarazIntegrationPrepare("task-a")
                self.assertEqual(self.pending(), [])

    def test_ui_contract_requires_prepare_then_queue_and_manual_scoped_history(self):
        app = (Path(__file__).resolve().parents[1] / "src" / "App.jsx").read_text(
            encoding="utf-8"
        )
        start = app.index("const sendToTaraz=async(taskId,requestId=null)=>{")
        end = app.index("if(!data)return", start)
        sender = app[start:end]
        self.assertLess(sender.index("if(!tarazEnabled)"), sender.index(
            "api.tarazIntegrationPrepare(taskId)"
        ))
        self.assertLess(sender.index("if(dirty.current||saving.current||blocked.current)"),
                        sender.index("api.tarazIntegrationPrepare(taskId)"))
        self.assertLess(sender.index("api.tarazIntegrationPrepare(taskId)"),
                        sender.index("api.tarazIntegrationQueue(taskId,null,targetId)"))
        self.assertIn("result?.postingPerformed!==false", sender)
        self.assertRegex(app, r"api\.tarazIntegrationHistory\(task\.id,true\)")
        self.assertIn("if(!window.confirm(", app)
        self.assertIn("item?.state!=='pending'", app)
        self.assertIn("tarazQueueAvailable={tarazEnabled&&tarazStatus?.supported===true", app)
        self.assertTrue(all(callable(getattr(native_app.Bridge, name, None))
                            for name in ("tarazIntegrationPrepare", "tarazIntegrationQueue",
                                         "tarazIntegrationHistory")))


if __name__ == "__main__":
    unittest.main()
