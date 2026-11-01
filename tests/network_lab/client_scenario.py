"""One real Madar Bridge in its own Python process and disposable Windows profile.

The parent speaks JSON lines on stdin/stdout. No simulated Bridge/HTTP transport is
used. All client files resolve below APPDATA set by run_multi_client.py.
"""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import sys


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import native_app
from lan import pinned_https_json


def _safe_state(state, bridge):
    return {
        "projects": [project["id"] for project in state["projects"]],
        "tasks": {task["id"]: task["title"] for task in state["tasks"]},
        "revision": state.get("__remoteRevision"),
        "offline": bool(state.get("__offline", False)),
        "pending": bridge.offline.has_pending(),
    }


def serve():
    # The harness provides fresh APPDATA and LOCALAPPDATA; refuse real profiles.
    scope = Path(os.environ["MADAR_NETWORK_LAB_PROFILE"]).resolve()
    for key in ("APPDATA", "LOCALAPPDATA"):
        resolved = Path(os.environ[key]).resolve()
        if not resolved.is_relative_to(scope):
            raise RuntimeError(f"{key} is not inside the disposable lab profile")
    bridge = native_app.Bridge()
    snapshot = None
    staged = None
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
            command = message["command"]
            if command == "connect":
                status = bridge.lanJoin(message["url"], message["username"],
                                        message["password"], message["fingerprint"])
                result = {"username": status["user"]["username"],
                          "role": status["user"]["role"],
                          "mode": status["mode"], "transport": status["transport"]}
            elif command == "snapshot":
                snapshot = deepcopy(bridge.getState())
                result = _safe_state(snapshot, bridge)
            elif command == "stage":
                if snapshot is None:
                    raise RuntimeError("snapshot required")
                staged = deepcopy(snapshot)
                matches = [task for task in staged["tasks"]
                           if task["id"] == message["task_id"]]
                if len(matches) != 1:
                    raise ValueError("task not in this user's project scope")
                matches[0]["title"] = message["title"]
                result = {"staged": message["task_id"]}
            elif command == "write":
                if staged is None:
                    raise RuntimeError("stage required")
                saved = bridge.saveState(deepcopy(staged))
                result = {"offline": saved.get("offline", False),
                          "pending": bridge.offline.has_pending()}
            elif command == "direct":
                # Direct HTTPS endpoint checks exercise server ACL and CAS even
                # when Bridge rejects a viewer save before making a request.
                data = message.get("payload")
                if message.get("write_snapshot"):
                    if snapshot is None:
                        raise RuntimeError("snapshot required")
                    data = {"state": {key: value for key, value in snapshot.items()
                                      if not key.startswith("__")},
                            "revision": snapshot["__remoteRevision"]}
                headers = {"Authorization": "Bearer " + bridge.remote_token}
                url = bridge.connection["url"] + message["endpoint"]
                payload = pinned_https_json(
                    url, bridge.connection["fingerprint"],
                    method="POST" if data is not None else "GET",
                    data=data, headers=headers, timeout=4)
                result = {"accepted": True,
                          "keys": sorted(payload) if isinstance(payload, dict) else []}
            elif command == "wrong_pin":
                # No secret is sent if the TLS fingerprint mismatches.
                pinned_https_json(
                    bridge.connection["url"] + "/api/login", "0" * 64,
                    method="POST", data={"username": "synthetic-check",
                                         "password": "not-a-credential"}, timeout=4)
                result = {"unexpectedly_accepted": True}
            elif command == "leave":
                bridge.lanLeave()
                snapshot = staged = None
                result = {"mode": bridge.connection["mode"]}
            elif command == "discard_synthetic_pending":
                # Test fixture cleanup ONLY. The parent supplied an isolated
                # APPDATA tree and has already recorded the conflict outcome.
                pending = bridge.offline.pending.resolve()
                if not pending.is_relative_to(scope):
                    raise RuntimeError("pending file escaped lab profile")
                existed = pending.exists()
                pending.unlink(missing_ok=True)
                result = {"discardedLabConflict": existed}
            elif command == "identity":
                result = {"mode": bridge.connection.get("mode"),
                          "username": (bridge.remote_user or {}).get("username"),
                          "profile": str(scope),
                          "has_pin": len(bridge.connection.get("fingerprint", "")) == 64}
            elif command == "shutdown":
                result = {"closed": True}
            else:
                raise ValueError("unsupported lab command")
            output = {"ok": True, "result": result}
        except Exception as exc:
            # Deliberately do not echo token or credentials into evidence files.
            output = {"ok": False, "errorType": type(exc).__name__,
                      "error": str(exc)[:240]}
        sys.stdout.write(json.dumps(output, ensure_ascii=False) + "\n")
        sys.stdout.flush()
        if message.get("command") == "shutdown":
            return


if __name__ == "__main__":
    serve()
