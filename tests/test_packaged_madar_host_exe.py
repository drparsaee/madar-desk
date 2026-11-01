"""Opt-in isolated end-to-end smoke of the packaged Windows Host executable.

The test runs only if the locally built release/MadarHost.exe is present.
No service installation, real APPDATA, production TLS key or network adapter is
used. Every spawned process is owned by this test and explicitly cleaned up.
"""

from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import unittest

try:
    import psutil
except ImportError:
    psutil = None

from lan import pinned_https_json, certificate_fingerprint
from madar_host_service import provision_authority
from native_app import initial_state, normalize_state
from test_lan_tls import _CERT, _KEY  # Public disposable test fixture ONLY.


ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "release" / "MadarHost.exe"


def _unused_loopback_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _stop_own_process(process):
    if psutil is not None:
        try:
            parent = psutil.Process(process.pid)
            descendants = parent.children(recursive=True)
        except psutil.NoSuchProcess:
            descendants = []
        for child in descendants:
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass
        psutil.wait_procs(descendants, timeout=4)
        for child in descendants:
            try:
                if child.is_running():
                    child.kill()
            except psutil.NoSuchProcess:
                pass
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=4)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=4)


@unittest.skipUnless(os.name == "nt" and EXE.is_file() and psutil is not None,
                     "Requires a built MadarHost.exe on Windows and psutil")
class PackagedHostExecutableTest(unittest.TestCase):
    def test_packaged_console_https_host_keeps_state_after_forced_exit(self):
        with tempfile.TemporaryDirectory(prefix="madar-packaged-host-runtime-") as directory:
            root = Path(directory)
            tls = root / "tls"
            tls.mkdir()
            (tls / "cert.pem").write_text(_CERT, encoding="ascii")
            (tls / "key.pem").write_text(_KEY, encoding="ascii")
            password = "synthetic-host-only-password-2026"
            provision_authority(root, "qaowner", password_reader=lambda _: password)
            pin = certificate_fingerprint(tls / "cert.pem")
            port = _unused_loopback_port()
            base = f"https://127.0.0.1:{port}"

            def run_and_read():
                process = subprocess.Popen(
                    [str(EXE), "console", "--data-dir", str(root), "--port", str(port),
                     "--bind", "127.0.0.1"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                try:
                    last_error = None
                    for _ in range(30):
                        if process.poll() is not None:
                            self.fail(f"Packaged HTTPS Host exited during startup: {process.returncode}")
                        try:
                            login = pinned_https_json(base + "/api/login", pin,
                                method="POST", data={"username": "qaowner", "password": password})
                            token = login["token"]
                            result = pinned_https_json(base + "/api/state", pin,
                                headers={"Authorization": "Bearer " + token})
                            return token, result, process
                        except (ConnectionError, OSError) as error:
                            last_error = error
                            time.sleep(.3)
                    self.fail("Packaged HTTPS Host never became ready: " + repr(last_error))
                except BaseException:
                    _stop_own_process(process)
                    raise

            token, result, process = run_and_read()
            try:
                # The actual packaged host must start EMPTY on first run.
                # For this synthetic edit-and-restart contract, explicitly
                # create sample cards via the authorized HTTPS API, rather
                # than changing production first-run or the packaged binary.
                self.assertEqual(result["state"]["tasks"], [])
                result = pinned_https_json(
                    base + "/api/state", pin, method="POST",
                    data={"state": normalize_state(initial_state()),
                          "revision": result["revision"]},
                    headers={"Authorization": "Bearer " + token})
                self.assertTrue(result["state"]["tasks"])
                edited = result["state"]
                edited["tasks"][0]["title"] = "Packaged Host persistent QA task"
                pinned_https_json(base + "/api/state", pin, method="POST",
                    data={"state": edited, "revision": result["revision"]},
                    headers={"Authorization": "Bearer " + token})
            finally:
                _stop_own_process(process)

            # Forced stop is deliberate within the disposable test authority;
            # this tests restart, not physical loss of power or durability.
            _, restored, process = run_and_read()
            try:
                self.assertEqual(restored["state"]["tasks"][0]["title"],
                                 "Packaged Host persistent QA task")
            finally:
                _stop_own_process(process)


if __name__ == "__main__":
    unittest.main()
