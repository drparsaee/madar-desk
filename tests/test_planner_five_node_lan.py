"""Five *process* LAN regression, with real loopback TCP and isolated test profiles.

The peer processes emulate one host and four Windows desktop clients. This is
NOT a claim that five virtual machines, network adapters or cables were used.
Every peer receives a separate disposable APPDATA and LOCALAPPDATA directory.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "only-disposable-peer-password"


def _peer():
    """Line-oriented test controller inside an independent Windows process."""
    import native_app
    from lan import LanService

    bridge = native_app.Bridge()
    server = None

    def handle(message):
        nonlocal server
        action = message["action"]
        if action == "host":
            bridge.saveState(native_app.initial_state())
            server = LanService(bridge, bridge.lan_users_path, "127.0.0.1", 0)
            server.setup_owner("admin", PASSWORD)
            port = server.start()
            bridge.lan = server
            bridge.connection = {"mode": "server", "port": port}
            return {"url": f"http://127.0.0.1:{port}", "pid": os.getpid()}
        if action == "stop_host":
            server.stop()
            return {"stopped": True}
        if action == "resume_host":
            port = server.start()
            return {"url": f"http://127.0.0.1:{port}"}
        if action == "join":
            status = bridge.lanJoin(message["url"], message["user"], PASSWORD)
            return {"mode": status["mode"], "username": status["user"]["username"],
                    "pid": os.getpid()}
        if action == "rejoin":
            bridge.lanLeave()
            status = bridge.lanJoin(message["url"], message["user"], PASSWORD)
            return {"username": status["user"]["username"]}
        if action == "network_state":
            state = bridge.getState()
            return {"offline": bool(state.get("__offline")),
                    "projects": [p["id"] for p in state["projects"]],
                    "titles": [t["title"] for t in state["tasks"]],
                    "mode": bridge.lanStatus()["mode"]}
        if action == "edit_network":
            state = bridge.getState()
            state["tasks"][0]["title"] = message["title"]
            return bridge.saveState(state)
        if action == "planner_write":
            identity = message["identity"]
            entry = {"id": "qa-" + message["marker"], "title": message["marker"],
                     "notes": "private", "createdDate": "2026-11-03",
                     "dueDate": "", "doneAt": "", "repeatAnchor": "",
                     "remindTime": "", "dismissedFor": "",
                     "repeat": {"frequency": "none", "interval": 1,
                                "calendar": "gregorian"}}
            state = {"version": 1, "inbox": [entry], "entries": []}
            return bridge.plannerWrite(identity, state)
        if action == "planner_read":
            return bridge.plannerRead(message["identity"])
        if action == "current_identity":
            status = bridge.lanStatus()
            username = (status.get("user") or {}).get("username", "local")
            if status["mode"] == "client":
                parts = ["client", status["url"], status["fingerprint"], username]
            else:
                parts = [status["mode"], username]
            return {"identity": json.dumps(parts, separators=(",", ":"),
                                           ensure_ascii=False)}
        raise ValueError("Unknown synthetic peer operation")

    try:
        for line in sys.stdin:
            try:
                result = handle(json.loads(line))
                output = {"ok": True, "result": result}
            except Exception as error:
                output = {"ok": False, "error": type(error).__name__ + ": " + str(error)}
            print(json.dumps(output, ensure_ascii=True), flush=True)
    finally:
        if server:
            server.stop()


class Peer:
    def __init__(self, root: Path):
        env = os.environ.copy()
        env["APPDATA"] = str(root / "Roaming")
        env["LOCALAPPDATA"] = str(root / "Local")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        self.process = subprocess.Popen(
            [sys.executable, "-B", "-m", "tests.test_planner_five_node_lan", "--peer"],
            cwd=str(ROOT), env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf8",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def command(self, action, **params):
        assert self.process.poll() is None, "peer process exited unexpectedly"
        self.process.stdin.write(json.dumps({"action": action, **params}) + "\n")
        self.process.stdin.flush()
        # Calls are serialized per peer; the parent controls all read deadlines.
        line = self.process.stdout.readline()
        if not line:
            raise AssertionError("peer response missing; exit=" + str(self.process.poll()))
        message = json.loads(line)
        if not message["ok"]:
            raise RuntimeError(message["error"])
        return message["result"]

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=8)
        for handle in (self.process.stdout, self.process.stderr):
            handle.close()


def request(base, endpoint, payload=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    raw = json.dumps(payload).encode("utf8") if payload is not None else None
    with urlopen(Request(base + endpoint, raw, headers=headers), timeout=8) as response:
        return json.loads(response.read())


class PlannerFivePeerLanTests(unittest.TestCase):
    def test_five_separate_windows_processes_with_real_tcp_and_isolated_planner(self):
        with tempfile.TemporaryDirectory(prefix="madar-planner-five-process-") as folder:
            root = Path(folder)
            peers = [Peer(root / f"node-{i}") for i in range(1, 6)]
            try:
                # An actual listener and four remote HTTP clients, no mock network.
                with ThreadPoolExecutor(max_workers=1) as pool:
                    base = pool.submit(peers[0].command, "host").result(timeout=18)["url"]
                owner = request(base, "/api/login", {"username": "admin", "password": PASSWORD})["token"]
                roles = (("editor-a", "editor"), ("editor-b", "editor"),
                         ("viewer-a", "viewer"), ("viewer-b", "viewer"))
                for username, role in roles:
                    request(base, "/api/user", {"username": username, "password": PASSWORD,
                                                "role": role, "projects": ["p-sample"]}, owner)
                pids = {peers[0].command("current_identity")["identity"]: peers[0].process.pid}
                identities = []
                for node, (username, role) in zip(peers[1:], roles):
                    result = node.command("join", url=base, user=username)
                    self.assertEqual((result["mode"], result["username"]),
                                     ("client", username))
                    self.assertEqual(len(node.command("network_state")["projects"]), 1)
                    identity = node.command("current_identity")["identity"]
                    identities.append(identity)
                    pids[identity] = result["pid"]
                self.assertEqual(len(set(pids.values())), 5)
                self.assertEqual(len(set(identities)), 4)

                # Native Planner persistence is device-local even when task data
                # is shared through LAN; use the real generated JSON identities.
                host_identity = peers[0].command("current_identity")["identity"]
                self.assertEqual(host_identity, '["server","admin"]')
                for index, (node, identity) in enumerate(zip(peers, [host_identity, *identities])):
                    self.assertIsNone(node.command("planner_read", identity=identity))
                    saved = node.command("planner_write", identity=identity,
                                         marker=f"peer-{index}")
                    self.assertEqual(saved["inbox"][0]["title"], f"peer-{index}")
                for index, (node, identity) in enumerate(zip(peers, [host_identity, *identities])):
                    self.assertEqual(node.command("planner_read", identity=identity)["inbox"][0]["title"],
                                     f"peer-{index}")
                    self.assertFalse(any((root / f"node-{j}" / "Roaming" / "MadarDesk" /
                                          "planner-private-v1").samefile(
                                              root / f"node-{index+1}" / "Roaming" /
                                              "MadarDesk" / "planner-private-v1")
                                         for j in range(1, 6) if j != index+1))

                # Viewer writes to LAN are rejected at the native bridge.
                for node in peers[3:]:
                    with self.assertRaisesRegex(RuntimeError, "PermissionError"):
                        node.command("edit_network", title="forbidden-viewer")
                # Authoritative server also enforces it over TCP, bypassing UI.
                viewer_token = request(base, "/api/login", {"username": "viewer-a",
                                                              "password": PASSWORD})["token"]
                view = request(base, "/api/state", token=viewer_token)
                with self.assertRaises(HTTPError) as denied:
                    request(base, "/api/state", {"state": view["state"],
                                                   "revision": view["revision"]}, viewer_token)
                self.assertEqual(denied.exception.code, 403)

                # Stale concurrent edit attempts must yield exactly one commit.
                edit_tokens = [request(base, "/api/login", {"username": name,
                                                             "password": PASSWORD})["token"]
                               for name in ("editor-a", "editor-b")]
                snapshots = [request(base, "/api/state", token=t) for t in edit_tokens]
                for index, snapshot in enumerate(snapshots):
                    snapshot["state"]["tasks"][0]["title"] = "parallel-" + str(index)

                def post(index):
                    try:
                        request(base, "/api/state", {"state": snapshots[index]["state"],
                                                      "revision": snapshots[index]["revision"]},
                                edit_tokens[index])
                        return 200
                    except HTTPError as error:
                        return error.code

                with ThreadPoolExecutor(max_workers=2) as pool:
                    statuses = list(pool.map(post, (0, 1)))
                self.assertEqual(sorted(statuses), [200, 409])

                # Disconnect affects shared task synchronization, not any peer's
                # private Planner. Reconnecting restores the same LAN identity.
                self.assertTrue(peers[0].command("stop_host")["stopped"])
                offline = peers[1].command("network_state")
                self.assertTrue(offline["offline"])
                self.assertEqual(peers[1].command("planner_read", identity=identities[0])[
                    "inbox"][0]["title"], "peer-1")
                self.assertEqual(peers[0].command("resume_host")["url"], base)
                online = peers[1].command("network_state")
                self.assertFalse(online["offline"])
                self.assertEqual(peers[1].command("planner_read", identity=identities[0])[
                    "inbox"][0]["title"], "peer-1")

                # Changing account on one Windows profile does not rebind its
                # Planner to the previous account's browser-selected namespace.
                self.assertEqual(peers[1].command("rejoin", url=base, user="editor-b")[
                    "username"], "editor-b")
                changed = peers[1].command("current_identity")["identity"]
                self.assertEqual(changed, identities[1])
                self.assertIsNone(peers[1].command("planner_read", identity=changed))
                self.assertEqual(peers[1].command("planner_read", identity=identities[0])[
                    "inbox"][0]["title"], "peer-1")
            finally:
                for peer in reversed(peers):
                    peer.close()


if __name__ == "__main__":
    if "--peer" in sys.argv:
        _peer()
    else:
        unittest.main()
