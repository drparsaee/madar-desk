"""Bounded multi-PROCESS network lab using Madar's actual Bridge and HTTPS LAN.

Run: python tests/network_lab/run_multi_client.py
Output: tests/network_lab/evidence_latest.json

Only the loopback interface is used; temporary profiles are created under this
directory, never in the real Windows APPDATA/LOCALAPPDATA. Test credentials and
the TLS key come from the repository's public, test-only fixtures.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import native_app
from lan import LanService, certificate_fingerprint, pinned_https_json
from test_lan_tls import _CERT, _KEY


PASSWORD = "network-lab-only-synthetic-password"
EVIDENCE = HERE / "evidence_latest.json"


class LabClient:
    def __init__(self, name, scope):
        self.name = name
        self.scope = scope
        roaming = scope / "roaming"
        local = scope / "local"
        roaming.mkdir(parents=True, exist_ok=True)
        local.mkdir(parents=True, exist_ok=True)
        temporary = scope / "temporary"
        temporary.mkdir(exist_ok=True)
        env = {**os.environ, "APPDATA": str(roaming), "LOCALAPPDATA": str(local),
               "TEMP": str(temporary), "TMP": str(temporary),
               "TMPDIR": str(temporary),
               "MADAR_NETWORK_LAB_PROFILE": str(scope), "PYTHONUNBUFFERED": "1",
               "PYTHONIOENCODING": "utf-8"}
        self.stderr_stream = open(scope / "stderr.log", "w", encoding="utf8")
        self.process = subprocess.Popen(
            [sys.executable, "-u", str(HERE / "client_scenario.py")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self.stderr_stream, text=True, encoding="utf8",
            bufsize=1, env=env, cwd=str(ROOT),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.responses = queue.Queue()
        self.reader = threading.Thread(target=self._read_responses, daemon=True)
        self.reader.start()

    def _read_responses(self):
        for line in self.process.stdout:
            self.responses.put(line)
        self.responses.put(None)

    def send(self, command, **kwargs):
        if self.process.poll() is not None:
            raise RuntimeError(f"client {self.name} exited: {self.process.returncode}")
        self.process.stdin.write(json.dumps({"command": command, **kwargs},
                                            ensure_ascii=False) + "\n")
        self.process.stdin.flush()
        try:
            response = self.responses.get(timeout=18)
        except queue.Empty as exc:
            raise TimeoutError(f"client {self.name} timed out: {command}") from exc
        if response is None:
            raise RuntimeError(f"client {self.name} exited during {command}")
        return json.loads(response)

    def close(self):
        try:
            if self.process.poll() is None:
                self.send("shutdown")
                self.process.wait(timeout=5)
        except (OSError, RuntimeError, TimeoutError, subprocess.TimeoutExpired):
            self.process.kill()
            self.process.wait(timeout=5)
        finally:
            self.stderr_stream.close()


def demand(response, *, allowed=(True,), error_contains=None, error_type=None):
    if response.get("ok") not in allowed:
        raise AssertionError(f"unexpected child outcome: {response}")
    if error_contains and error_contains not in response.get("error", ""):
        raise AssertionError(f"wrong error: {response}")
    if error_type and response.get("errorType") != error_type:
        raise AssertionError(f"wrong error type: {response}")
    return response.get("result", response)


def run():
    evidence = {
        "lab": "Madar real Bridge / multi-Python-process HTTPS loopback",
        "startedUtc": datetime.now(timezone.utc).isoformat(),
        "bind": "127.0.0.1",
        "syntheticOnly": True,
        "clients": {},
        "checks": [],
        "result": "running",
    }

    def check(name, predicate, details=None):
        passed = bool(predicate)
        evidence["checks"].append({"name": name, "passed": passed,
                                   **({"detail": details} if details is not None else {})})
        if not passed:
            raise AssertionError(f"{name}: {details}")

    clients = {}
    service = None
    with tempfile.TemporaryDirectory(prefix="run-", dir=str(HERE)) as temp:
        root = Path(temp)
        cert = root / "test-only.crt"
        key = root / "test-only.key"
        cert.write_text(_CERT, encoding="ascii")
        key.write_text(_KEY, encoding="ascii")
        host_profile = root / "host"
        host_profile.mkdir()
        host_temp = root / "host-temporary"
        host_temp.mkdir()
        host_environment = patch.dict(os.environ, {
            "APPDATA": str(host_profile), "LOCALAPPDATA": str(host_profile),
            "TEMP": str(host_temp), "TMP": str(host_temp), "TMPDIR": str(host_temp),
        })
        host_environment.start()
        former_tempdir = tempfile.tempdir
        tempfile.tempdir = str(host_temp)

        def make_host_bridge():
            # Patch only while constructing the actual Bridge. Host file paths
            # stay bound to a synthetic directory after this context exits.
            with patch.object(native_app, "datadir", return_value=host_profile):
                return native_app.Bridge()

        def tls(endpoint, data=None, token=None):
            headers = {"Authorization": "Bearer " + token} if token else {}
            return pinned_https_json(url + endpoint, fingerprint,
                                     method="POST" if data is not None else "GET",
                                     data=data, headers=headers, timeout=6)

        try:
            host = make_host_bridge()
            host.saveState(native_app.initial_state())
            service = LanService(host, host_profile / "lan-users.json",
                                 bind="127.0.0.1", port=0,
                                 certfile=cert, keyfile=key)
            service.setup_owner("lab-owner", PASSWORD)
            port = service.start()
            url = f"https://127.0.0.1:{port}"
            fingerprint = certificate_fingerprint(cert)
            check("host-listens-on-loopback-only",
                  service.server.server_address[0] == "127.0.0.1")
            evidence["host"] = {"https": True, "ephemeralPort": port,
                                "tlsPinLength": len(fingerprint)}
            owner = tls("/api/login", {"username": "lab-owner",
                                       "password": PASSWORD})["token"]
            for name, role, projects in (
                ("lab-writer-a", "editor", ["p-sample"]),
                ("lab-writer-b", "editor", ["p-sample"]),
                ("lab-viewer", "viewer", ["p-personal"]),
            ):
                tls("/api/user", {"username": name, "password": PASSWORD,
                                  "role": role, "projects": projects}, owner)
                profile = root / "clients" / name
                profile.mkdir(parents=True)
                client = LabClient(name, profile)
                clients[name] = client
                connected = demand(client.send("connect", url=url, username=name,
                                               password=PASSWORD, fingerprint=fingerprint))
                check(f"login-{name}", connected["username"] == name and
                      connected["role"] == role and connected["transport"] == "https")
                identity = demand(client.send("identity"))
                check(f"profile-{name}", identity["profile"] == str(profile) and
                      identity["has_pin"] and identity["username"] == name)
                evidence["clients"][name] = {"pid": client.process.pid,
                                             "role": role, "projects": projects,
                                             "isolatedProfile": True}

            check("three-distinct-client-processes",
                  len({client.process.pid for client in clients.values()}) == 3)

            a = clients["lab-writer-a"]
            b = clients["lab-writer-b"]
            v = clients["lab-viewer"]
            va = demand(v.send("snapshot"))
            sa = demand(a.send("snapshot"))
            sb = demand(b.send("snapshot"))
            check("viewer-project-scope", va["projects"] == ["p-personal"] and not va["tasks"])
            check("editor-project-scope", sa["projects"] == ["p-sample"] and len(sa["tasks"]) >= 2)

            for name, message in (
                ("viewer-state-write", v.send("direct", endpoint="/api/state", write_snapshot=True)),
                ("viewer-user-list", v.send("direct", endpoint="/api/users")),
                ("editor-user-create", a.send("direct", endpoint="/api/user", payload={
                    "username": "unauthorized", "password": PASSWORD, "role": "admin"})),
            ):
                check(name, message.get("ok") is False and message.get("errorType") == "HTTPError"
                      and "403" in message.get("error", ""), message.get("errorType"))
            demand(v.send("stage", task_id="example-1", title="viewer-illegal"),
                   allowed=(False,), error_contains="scope")
            prior_sessions = len(service.sessions)
            mismatch = b.send("wrong_pin")
            check("wrong-TLS-pin-refused", not mismatch["ok"] and
                  mismatch["errorType"] == "SSLCertVerificationError")
            check("wrong-pin-did-not-send-login",
                  len(service.sessions) == prior_sessions)

            demand(a.send("stage", task_id="example-1", title="race-writer-a"))
            demand(b.send("stage", task_id="example-1", title="race-writer-b"))
            with ThreadPoolExecutor(max_workers=2) as pool:
                fa = pool.submit(a.send, "write")
                fb = pool.submit(b.send, "write")
                ra, rb = fa.result(timeout=25), fb.result(timeout=25)
            check("concurrent-CAS-one-winner", sum(x["ok"] for x in (ra, rb)) == 1 and
                  any(not x["ok"] and "CONFLICT" in x.get("error", "") for x in (ra, rb)),
                  {"writerA": ra.get("ok"), "writerB": rb.get("ok")})
            winner = "race-writer-a" if ra["ok"] else "race-writer-b"
            check("CAS-host-winner-persisted", {t["id"]: t["title"] for t in
                  host.getState()["tasks"]}["example-1"] == winner)

            # A failed writer may have a pending conflicting queue. Explicitly
            # leave/rejoin inside the disposable profile for the next scenario.
            for client, name in ((a, "lab-writer-a"), (b, "lab-writer-b")):
                demand(client.send("leave"))
                demand(client.send("discard_synthetic_pending"))
                demand(client.send("connect", url=url, username=name,
                                   password=PASSWORD, fingerprint=fingerprint))
            before = demand(b.send("snapshot"))
            check("offline-client-base", before["pending"] is False)
            demand(b.send("stage", task_id="example-1", title="offline-nonoverlap"))
            service.stop()
            offline = demand(b.send("write"))
            check("offline-local-queue", offline["offline"] is True and offline["pending"] is True)
            current = host.getState()
            current["tasks"][1]["title"] = "host-nonoverlap"
            host.saveState(current)
            service.start()
            merged = demand(b.send("snapshot"))
            check("offline-reconcile-two-edits", merged["tasks"].get("example-1") == "offline-nonoverlap"
                  and merged["tasks"].get("example-2") == "host-nonoverlap"
                  and not merged["pending"])
            check("reconcile-durable-on-host", {t["id"]: t["title"] for t in
                  host.getState()["tasks"]}["example-1"] == "offline-nonoverlap")

            demand(a.send("snapshot"))
            demand(a.send("stage", task_id="example-1", title="offline-conflicting"))
            service.stop()
            conflict_offline = demand(a.send("write"))
            check("conflict-queued-offline", conflict_offline["offline"] and conflict_offline["pending"])
            current = host.getState()
            current["tasks"][0]["title"] = "host-conflicting"
            host.saveState(current)
            service.start()
            conflict = a.send("snapshot")
            check("same-card-conflict-protected", not conflict["ok"] and
                  "CONFLICT" in conflict.get("error", ""))
            check("host-not-overwritten-by-conflict", {t["id"]: t["title"] for t in
                  host.getState()["tasks"]}["example-1"] == "host-conflicting")

            # Clear the deliberately unresolved synthetic conflict before the
            # full restart so independent credential recovery can be assessed.
            demand(a.send("leave"))
            demand(a.send("discard_synthetic_pending"))
            demand(a.send("connect", url=url, username="lab-writer-a",
                                  password=PASSWORD, fingerprint=fingerprint))
            service.stop()
            service = None
            for client in clients.values():
                client.close()
            clients.clear()
            host = make_host_bridge()
            service = LanService(host, host_profile / "lan-users.json",
                                 bind="127.0.0.1", port=port,
                                 certfile=cert, keyfile=key)
            check("new-host-loads-three-accounts", len(service.users) == 4)
            service.start()
            for name in ("lab-writer-a", "lab-writer-b", "lab-viewer"):
                profile = root / "clients" / name
                client = LabClient(name, profile)
                clients[name] = client
                check(f"reboot-new-process-{name}",
                      client.process.pid != evidence["clients"][name]["pid"])
                identity = demand(client.send("identity"))
                check(f"reboot-reconnect-{name}", identity["mode"] == "client" and
                      identity["username"] == name and identity["has_pin"])
                result = demand(client.send("snapshot"))
                check(f"reboot-read-{name}", result["revision"] is not None and not result["offline"])
            surviving = {t["id"]: t["title"] for t in host.getState()["tasks"]}
            check("host-persistence-after-reboot", surviving["example-1"] == "host-conflicting"
                  and surviving["example-2"] == "host-nonoverlap")
            evidence["result"] = "passed"
        except Exception as exc:
            evidence["result"] = "failed"
            evidence["failure"] = {"type": type(exc).__name__, "message": str(exc)[:300]}
        finally:
            if service is not None:
                service.stop()
            for client in clients.values():
                client.close()
                log = client.scope / "stderr.log"
                if log.exists() and log.stat().st_size:
                    evidence.setdefault("clientErrors", {})[client.name] = log.read_text(
                        encoding="utf8", errors="replace")[-1200:]
            evidence["finishedUtc"] = datetime.now(timezone.utc).isoformat()
            evidence["passed"] = sum(entry["passed"] for entry in evidence["checks"])
            evidence["total"] = len(evidence["checks"])
            # No credentials, bearer tokens, paths to operational profiles or
            # certificate private keys are written to this evidence file.
            EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf8")
            tempfile.tempdir = former_tempdir
            host_environment.stop()
    return evidence


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf8")
    outcome = run()
    print(json.dumps({"result": outcome["result"], "passed": outcome["passed"],
                      "total": outcome["total"], "failure": outcome.get("failure"),
                      "evidence": str(EVIDENCE)}, ensure_ascii=False))
    sys.exit(0 if outcome["result"] == "passed" else 1)
