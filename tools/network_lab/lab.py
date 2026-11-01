"""Run real Madar HTTPS host and two desktop Bridges in disposable processes.

No service installation, real user profiles, non-loopback listeners or VMs.
All credentials and application data are created under tools/network_lab/.runs.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import ssl
import subprocess
import sys
import time
from urllib.error import HTTPError
import uuid


LAB_DIR = Path(__file__).resolve().parent
REPO = LAB_DIR.parents[1]
RUNS = LAB_DIR / ".runs"
EVIDENCE = LAB_DIR / "evidence"
HOST_NAME = "host"
CLIENT_EDITOR = "client-editor"
CLIENT_VIEWER = "client-viewer"
USERNAME_OWNER = "lab-owner"
USERNAME_EDITOR = "lab-editor"
USERNAME_VIEWER = "lab-viewer"
TARGET_TITLE = "Synthetic isolated HTTPS editor change"


def _inside(child: Path, parent: Path) -> bool:
    return child.resolve(strict=False).is_relative_to(parent.resolve(strict=False))


def _owned_run(run: Path) -> Path:
    """Reject any root outside our laboratory or containing redirected links."""
    if not re.fullmatch(r"[0-9a-f]{32}", run.name):
        raise ValueError("Invalid network lab run ID")
    if run.parent.resolve(strict=False) != RUNS.resolve(strict=False):
        raise ValueError("Run must be an immediate child of network_lab/.runs")
    if run.is_symlink() or not run.is_dir():
        raise ValueError("Run is absent or points to a link")
    marker = run / "lab-owner.json"
    if marker.is_symlink() or not marker.is_file():
        raise ValueError("Run ownership marker is missing")
    metadata = json.loads(marker.read_text(encoding="utf8"))
    if metadata != {"kind": "madar-isolated-network-lab", "run": run.name}:
        raise ValueError("Run ownership marker mismatch")
    return run


def _role_root(run: Path, role: str) -> Path:
    if role not in (HOST_NAME, CLIENT_EDITOR, CLIENT_VIEWER):
        raise ValueError("Unknown synthetic host/client role")
    target = run / role
    if not _inside(target, run) or target.is_symlink():
        raise ValueError("Unsafe role profile path")
    return target


def _role_env(run: Path, role: str, password: str) -> dict[str, str]:
    root = _role_root(run, role)
    folders = {
        "APPDATA": root / "AppData" / "Roaming",
        "LOCALAPPDATA": root / "AppData" / "Local",
        "TEMP": root / "tmp",
        "TMP": root / "tmp",
        "USERPROFILE": root / "profile",
        "HOME": root / "profile",
    }
    for folder in folders.values():
        folder.mkdir(parents=True, exist_ok=True)
    return {**os.environ, **{name: str(path) for name, path in folders.items()},
            "MADAR_LAB_RUN_ROOT": str(run),
            "MADAR_LAB_PASSWORD": password,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1"}


def _check_child(role: str) -> tuple[Path, Path, str]:
    supplied = os.environ.get("MADAR_LAB_RUN_ROOT", "")
    if not supplied:
        raise PermissionError("Lab child requires a synthetic run context")
    run = _owned_run(Path(supplied))
    root = _role_root(run, role)
    appdata = root / "AppData" / "Roaming"
    if (not _inside(Path(os.environ.get("APPDATA", "")), root)
            or Path(os.environ.get("APPDATA", "")).resolve() != appdata.resolve()):
        raise PermissionError("APPDATA must be under the synthetic profile")
    if not appdata.exists():
        raise ValueError("Synthetic profile does not exist")
    password = os.environ.get("MADAR_LAB_PASSWORD", "")
    if len(password) < 20:
        raise ValueError("Missing synthetic lab credential")
    sys.path.insert(0, str(REPO))
    return run, root, password


def _host():
    run, root, password = _check_child(HOST_NAME)
    from tests.test_lan_tls import _CERT, _KEY
    from lan import LanService, certificate_fingerprint
    import native_app

    cert_folder = root / "tls"
    cert_folder.mkdir(parents=True, exist_ok=True)
    cert = cert_folder / "cert.pem"
    key = cert_folder / "key.pem"
    # Public, test-only certificate. Its key is *not* a deployment secret.
    cert.write_text(_CERT, encoding="ascii")
    key.write_text(_KEY, encoding="ascii")
    bridge = native_app.Bridge()
    bridge.saveState(native_app.initial_state())
    lan = LanService(bridge, root / "users" / "lan-users.json", bind="127.0.0.1",
                     port=0, certfile=str(cert), keyfile=str(key))
    lan.users_path.parent.mkdir(parents=True, exist_ok=True)
    lan.setup_owner(USERNAME_OWNER, password)
    owner_token = lan.authenticate_owner_token()
    lan.upsert_user(owner_token, {"username": USERNAME_EDITOR, "role": "editor",
                                  "projects": ["p-sample"], "password": password})
    lan.upsert_user(owner_token, {"username": USERNAME_VIEWER, "role": "viewer",
                                  "projects": ["p-personal"], "password": password})
    try:
        port = lan.start()
        ready = run / "host-ready.json"
        tmp = ready.with_suffix(".tmp")
        tmp.write_text(json.dumps({"port": port, "pin": certificate_fingerprint(cert),
                                   "bind": lan.server.server_address[0],
                                   "tls": True}), encoding="utf8")
        os.replace(tmp, ready)
        while not (run / "stop.signal").exists():
            if not lan.thread or not lan.thread.is_alive():
                raise RuntimeError("Lab LAN thread stopped unexpectedly")
            time.sleep(0.1)
    finally:
        lan.stop()


def _client(role: str, stage: str, port: int, pin: str):
    _run, _root, password = _check_child(role)
    import native_app
    bridge = native_app.Bridge()
    base = f"https://127.0.0.1:{port}"
    username = USERNAME_EDITOR if role == CLIENT_EDITOR else USERNAME_VIEWER
    if stage == "pin-reject":
        try:
            bridge._remote_login(base, username, password, fingerprint="0" * 64)
        except ssl.SSLCertVerificationError:
            print(json.dumps({"check": "wrong_cert_pin_rejected", "passed": True}))
            return
        raise AssertionError("An incorrect pin was accepted")
    status = bridge.lanJoin(base, username, password, fingerprint=pin)
    if status.get("mode") != "client" or status.get("transport") != "https":
        raise AssertionError("Desktop Bridge did not join the HTTPS host")
    state = bridge.getState()
    if state.get("__offline"):
        raise AssertionError("Lab client unexpectedly running offline")
    visible = {p["id"] for p in state["projects"]}
    if role == CLIENT_EDITOR:
        if visible != {"p-sample"} or not state["tasks"]:
            raise AssertionError(f"Incorrect editor scope: {sorted(visible)}")
        if stage == "edit":
            state["tasks"][0]["title"] = TARGET_TITLE
            saved = bridge.saveState(state)
            if saved.get("offline") is not False:
                raise AssertionError("Editor write not committed to host")
        elif stage == "verify":
            if state["tasks"][0]["title"] != TARGET_TITLE:
                raise AssertionError("Independent editor process did not see committed change")
        else:
            raise ValueError("Invalid editor stage")
        print(json.dumps({"check": "editor_" + stage, "passed": True,
                          "projects": sorted(visible), "task_count": len(state["tasks"])}))
    else:
        if stage != "read-deny" or visible != {"p-personal"} or state["tasks"]:
            raise AssertionError("Viewer project visibility was incorrect")
        try:
            bridge.saveState(state)
        except PermissionError:
            # Verify server-side ACL too, even if the desktop correctly
            # refuses the same request without transmitting it.
            from lan import pinned_https_json
            attempted = {key: value for key, value in state.items()
                         if not key.startswith("__")}
            try:
                pinned_https_json(base + "/api/state", pin, method="POST",
                                  data={"state": attempted, "revision": bridge.remote_revision},
                                  headers={"Authorization": "Bearer " + bridge.remote_token},
                                  timeout=10)
            except HTTPError as error:
                if error.code != 403:
                    raise AssertionError(f"Host rejected viewer write with unexpected HTTP {error.code}")
            else:
                raise AssertionError("LAN host allowed a viewer write")
            print(json.dumps({"check": "viewer_scoped_and_readonly", "passed": True,
                              "host_denial": 403, "projects": sorted(visible),
                              "task_count": 0}))
            return
        raise AssertionError("Viewer was allowed to write")


def _launch_child(run: Path, role: str, password: str, args: list[str], *,
                  stdout=None, timeout: float = 35):
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    return subprocess.run([sys.executable, str(__file__), *args],
                          cwd=str(REPO), env=_role_env(run, role, password),
                          stdin=subprocess.DEVNULL, stdout=stdout or subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, timeout=timeout,
                          creationflags=flags, check=False)


def _run_lab(keep: bool) -> int:
    RUNS.mkdir(parents=True, exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    run = RUNS / uuid.uuid4().hex
    run.mkdir()
    (run / "lab-owner.json").write_text(json.dumps(
        {"kind": "madar-isolated-network-lab", "run": run.name}), encoding="utf8")
    password = secrets.token_urlsafe(32)
    host = None
    checked = []
    failure = None
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        log = (run / "host.log").open("w", encoding="utf8")
        try:
            host = subprocess.Popen([sys.executable, str(__file__), "host"],
                                    cwd=str(REPO), env=_role_env(run, HOST_NAME, password),
                                    stdin=subprocess.DEVNULL, stdout=log,
                                    stderr=subprocess.STDOUT, creationflags=flags)
        finally:
            log.close()
        deadline = time.monotonic() + 20
        ready = run / "host-ready.json"
        while not ready.exists() and time.monotonic() < deadline:
            if host.poll() is not None:
                raise RuntimeError("HTTPS host stopped before it was ready; inspect host.log")
            time.sleep(0.1)
        if not ready.exists():
            raise TimeoutError("HTTPS host did not become ready; inspect host.log")
        details = json.loads(ready.read_text(encoding="utf8"))
        if details["bind"] != "127.0.0.1" or details["tls"] is not True:
            raise AssertionError("Unexpected host topology")
        port, pin = details["port"], details["pin"]
        def check(role, stage):
            result = _launch_child(run, role, password,
                                   ["client", role, stage, str(port), pin])
            if result.returncode:
                # Error details remain under the disposable lab directory.
                (run / f"failure-{role}-{stage}.log").write_text(
                    result.stdout + "\n" + result.stderr, encoding="utf8")
                raise RuntimeError(f"{role}/{stage} failed with exit code {result.returncode}")
            payload = json.loads(result.stdout.strip())
            if payload.get("passed") is not True:
                raise AssertionError(f"{role}/{stage} did not report success")
            return payload

        checked.append(check(CLIENT_EDITOR, "pin-reject"))
        checked.append(check(CLIENT_EDITOR, "edit"))
        # Both independent desktop clients now query the same live host in
        # overlapping process lifetimes, using distinct user profiles.
        with ThreadPoolExecutor(max_workers=2) as executor:
            viewer_future = executor.submit(check, CLIENT_VIEWER, "read-deny")
            editor_future = executor.submit(check, CLIENT_EDITOR, "verify")
            checked.extend([viewer_future.result(), editor_future.result()])
        # Confirm that editor and viewer wrote to distinct synthetic profiles.
        for role in (HOST_NAME, CLIENT_EDITOR, CLIENT_VIEWER):
            expected = _role_root(run, role) / "AppData" / "Roaming" / "MadarDesk"
            if not (expected / "tasks.json").is_file():
                raise AssertionError(f"Synthetic {role} application store is absent")
        checked.append({"check": "three_distinct_appdata_stores", "passed": True})
    except Exception as exc:
        failure = f"{type(exc).__name__}: {exc}"
    finally:
        (run / "stop.signal").write_text("stop", encoding="ascii")
        if host is not None:
            try:
                host.wait(timeout=5)
            except subprocess.TimeoutExpired:
                host.terminate()
                try:
                    host.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    host.kill()
                    host.wait(timeout=5)
            if host.returncode not in (0, None) and failure is None:
                failure = f"HTTPS host exited with code {host.returncode}"
        if failure is None:
            try:
                host_data = _role_root(run, HOST_NAME) / "AppData" / "Roaming" / "MadarDesk" / "tasks.json"
                written = json.loads(host_data.read_text(encoding="utf8"))
                if written["tasks"][0]["title"] != TARGET_TITLE:
                    raise AssertionError("Synthetic host disk lacks the editor's committed change")
                checked.append({"check": "host_durable_disk_write", "passed": True})
            except Exception as exc:
                failure = f"{type(exc).__name__}: {exc}"
        summary = {"run": run.name, "passed": failure is None, "checks": checked,
                   "error": failure, "topology": {
                       "host": "separate Python process + native_app.Bridge + LanService",
                       "clients": "two isolated native_app.Bridge profiles in independent processes",
                       "network": "HTTPS over 127.0.0.1 ephemeral TCP port; no external LAN",
                       "tls": "pinned public test-only certificate"},
                   "kept": keep}
        # Evidence contains no passwords, session tokens, or customer records.
        (EVIDENCE / "last-run.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf8")
        if not keep:
            _clean_run(run)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if failure is None else 1


def _clean_run(run: Path):
    _owned_run(run)
    if (run / "host-ready.json").exists() and not (run / "stop.signal").exists():
        raise RuntimeError("Refusing cleanup of a potentially running lab host")
    shutil.rmtree(run)


def _probe() -> None:
    """Read-only Windows feature and WSL inspection, never feature activation."""
    import platform
    facts = {"platform": platform.platform(), "python": sys.version.split()[0],
             "repo": str(REPO),
             "recommendation": "Isolated loopback processes; no VM creation"}
    if os.name == "nt":
        script = (
            "$features=@('Microsoft-Hyper-V-All','VirtualMachinePlatform',"
            "'Microsoft-Windows-Subsystem-Linux'); "
            "$featureState=@{}; foreach($f in $features){ "
            "try {$featureState[$f]=(Get-WindowsOptionalFeature -Online -FeatureName $f -ErrorAction Stop).State.ToString()} "
            "catch {$featureState[$f]='UNKNOWN'} }; "
            "$hv=(Get-CimInstance -ClassName Win32_ComputerSystem).HypervisorPresent; "
            "$vm=Get-Service vmcompute,vmms -ErrorAction SilentlyContinue | "
            "Select-Object Name,Status; "
            "[pscustomobject]@{HypervisorPresent=$hv; Features=$featureState; Services=@($vm)} "
            "| ConvertTo-Json -Depth 4 -Compress"
        )
        try:
            completed = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                timeout=30, check=False)
            facts["windows_features"] = (json.loads(completed.stdout.strip())
                                         if completed.returncode == 0 else "UNKNOWN")
        except (OSError, ValueError, subprocess.TimeoutExpired):
            facts["windows_features"] = "UNKNOWN"
        try:
            distro = subprocess.run(["wsl.exe", "--list", "--verbose"],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    timeout=15, check=False)
            raw = distro.stdout
            facts["wsl_distributions"] = (raw.decode("utf-16-le", errors="replace")
                                           if b"\x00" in raw[:20] else
                                           raw.decode("utf-8", errors="replace")).replace("\ufeff", "").strip()
            facts["wsl_status"] = "OK" if distro.returncode == 0 else "UNKNOWN"
        except (OSError, subprocess.TimeoutExpired):
            facts["wsl_status"] = "UNKNOWN"
    print(json.dumps(facts, ensure_ascii=False, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Run HTTPS host + two isolated desktop client processes")
    run.add_argument("--keep", action="store_true", help="Keep disposable data and logs in .runs/<id>")
    sub.add_parser("probe", help="Print environment facts without changing system state")
    clean = sub.add_parser("cleanup", help="Remove an owned stopped lab run")
    clean.add_argument("run_id")
    child = sub.add_parser("client", help=argparse.SUPPRESS)
    child.add_argument("role", choices=[CLIENT_EDITOR, CLIENT_VIEWER])
    child.add_argument("stage", choices=["pin-reject", "edit", "read-deny", "verify"])
    child.add_argument("port", type=int)
    child.add_argument("pin")
    sub.add_parser("host", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.command == "run":
        return _run_lab(args.keep)
    if args.command == "probe":
        _probe()
    elif args.command == "cleanup":
        _clean_run(RUNS / args.run_id)
        print("Removed synthetic network lab run", args.run_id)
    elif args.command == "host":
        _host()
    elif args.command == "client":
        _client(args.role, args.stage, args.port, args.pin)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
