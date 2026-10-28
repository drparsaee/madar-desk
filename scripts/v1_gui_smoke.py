"""Madar Desk v1 RC1 Windows GUI smoke, with isolated state and owned processes.

Usage (only a freshly built, unique candidate owned by the QA runner):
    py -3.12 scripts/v1_gui_smoke.py --exe release/Madar-Desk-v1.0-rcNEXT.exe
    py -3.12 scripts/v1_gui_smoke.py --exe release/Madar-Desk-v1.0-rcNEXT.exe --interactive

The executable must implement MADAR_QA_REPORT. This runner launches a single
Windows process suspended into its *own* Windows Job Object before it resumes.
Closing the Job kills only processes owned by that Job, including PyInstaller
children. It never scans or kills a process by executable name.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import time
import zlib
from typing import Any, Callable


PROJECT = Path(__file__).resolve().parent.parent
DEFAULT_EXE = PROJECT / "release" / "Madar-Desk-v1.0-rc1.exe"
MAX_REPORT_BYTES = 512_000
MAX_SCREENSHOT_BYTES = 30_000_000
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
EXIT_PASS, EXIT_FAIL, EXIT_MISSING, EXIT_UNSUPPORTED = 0, 1, 2, 3

# Actual independent /accounting.html route (src/standalone_main.jsx).
# Missing or legacy-only QA hooks fail closed; no financial mutation.
INTERACTIVE_REQUIRED = (
    "initial_rtl_and_board", "accounting_nav_visible",
    "finance_snapshot_captured", "standalone_snapshot_captured",
    "standalone_currency_rial_head",
    "accounting_workspace_opens", "accounting_workspace_fullscreen",
    "accounting_overview_selected",
    "accounting_navigation_payments", "accounting_payments_visible",
    "accounting_navigation_reports", "accounting_reports_visible",
    "accounting_currency_rial_display",
    "close_accounting_workspace", "accounting_workspace_closed",
    "finance_unchanged", "standalone_unchanged",
    "create_task_opens", "create_card_composer", "fill_task_title",
    "create_task_submit", "new_card_visible", "task_saved_to_host",
    "finance_unchanged_after_task", "standalone_unchanged_after_task",
)


class SmokeError(RuntimeError):
    """Expected and safely displayable smoke-harness failure."""


def safe_exe_path(candidate: Path, *, release_root: Path | None = None) -> Path:
    """Accept only a real release .exe; never run arbitrary user paths."""
    root = (release_root or PROJECT / "release").resolve()
    requested = candidate.resolve()
    if requested.suffix.lower() != ".exe" or not requested.is_relative_to(root):
        raise SmokeError("EXE must be inside the project's release directory")
    if not requested.is_file():
        raise FileNotFoundError(f"RC1 executable not found: {requested}")
    return requested


def isolated_environment(base: dict[str, str], scratch: Path, *, screenshot: bool,
                         interactive: bool = False) -> dict[str, str]:
    """Create new per-run profile/env without changing global os.environ."""
    paths = {
        "APPDATA": scratch / "AppData" / "Roaming",
        "LOCALAPPDATA": scratch / "AppData" / "Local",
        "TEMP": scratch / "Temp",
        "TMP": scratch / "Temp",
        "WEBVIEW2_USER_DATA_FOLDER": scratch / "WebView2",
    }
    for value in set(paths.values()):
        value.mkdir(parents=True, exist_ok=False)
    env = dict(base)
    for name in ("MADAR_QA_REPORT", "MADAR_QA_SCREENSHOT", "MADAR_QA_VIEW", "MADAR_QA_THEME", "MADAR_QA_INTERACTION"):
        env.pop(name, None)
    env.update({key: str(value) for key, value in paths.items()})
    env["MADAR_QA_REPORT"] = str(scratch / "diagnostics.json")
    env["MADAR_QA_VIEW"] = "sample-project"  # click seeded sample project to show cards
    env["MADAR_RELEASE_QA"] = "1"
    if interactive:
        env["MADAR_QA_INTERACTION"] = "1"
    if screenshot:
        env["MADAR_QA_SCREENSHOT"] = str(scratch / "screenshot.png")
    return env


def _safe_int(value: object, minimum: int, maximum: int) -> bool:
    return type(value) is int and minimum <= value <= maximum


def verify_png_complete(path: Path) -> dict[str, int]:
    """Validate the *complete* PNG file, chunk CRCs and IDAT zlib stream.

    A header-only PNG is never accepted. Bounded dimensions, compressed file
    bytes and decompressed bytes protect this release-QA helper from oversized
    input. This is file-integrity validation, not a visual content assertion.
    """
    if not path.is_file() or not 60 <= path.stat().st_size <= MAX_SCREENSHOT_BYTES:
        raise SmokeError("PNG absent, empty or exceeds file size limit")
    data = path.read_bytes()
    if len(data) > MAX_SCREENSHOT_BYTES or not data.startswith(PNG_MAGIC):
        raise SmokeError("invalid PNG signature")
    pos, width, height, chunk_count = len(PNG_MAGIC), 0, 0, 0
    row_bytes = 0
    idat = []
    seen_iend = False
    while pos < len(data):
        if pos + 12 > len(data):
            raise SmokeError("truncated PNG chunk")
        size = struct.unpack_from(">I", data, pos)[0]
        name = data[pos + 4:pos + 8]
        stop = pos + 12 + size
        if size > MAX_SCREENSHOT_BYTES or stop > len(data):
            raise SmokeError("incomplete PNG chunk data")
        contents = data[pos + 8:stop - 4]
        expected_crc = struct.unpack_from(">I", data, stop - 4)[0]
        actual_crc = zlib.crc32(name + contents) & 0xFFFFFFFF
        if expected_crc != actual_crc:
            raise SmokeError("PNG chunk CRC mismatch")
        chunk_count += 1
        if chunk_count > 25000:
            raise SmokeError("too many PNG chunks")
        if chunk_count == 1:
            if name != b"IHDR" or len(contents) != 13:
                raise SmokeError("PNG lacks valid initial IHDR")
            width, height, depth, color, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", contents
            )
            if (not 100 <= width <= 8192 or not 100 <= height <= 8192
                    or width * height > 22_000_000
                    or depth not in (8, 16) or color not in (0, 2, 4, 6)
                    or compression != 0 or filtering != 0 or interlace != 0):
                raise SmokeError("unsupported PNG dimensions or pixel format")
            # Native Edge WebView2 preview screenshots are noninterlaced.
            # Requiring exact scanline bytes rejects CRC-valid but empty IDATs.
            channels = {0: 1, 2: 3, 4: 2, 6: 4}[color]
            row_bytes = width * channels * (depth // 8)
        elif name == b"IHDR":
            raise SmokeError("duplicate PNG IHDR")
        if name == b"IDAT":
            idat.append(contents)
        elif name == b"IEND":
            if size != 0 or stop != len(data) or not idat:
                raise SmokeError("invalid, premature or non-final PNG IEND")
            seen_iend = True
            break
        pos = stop
    if not seen_iend:
        raise SmokeError("PNG has no complete IEND")
    decoder = zlib.decompressobj()
    output_size = 0
    maximum_output = 100_000_000
    raster = bytearray()
    for chunk in idat:
        remaining = chunk
        while remaining:
            decompressed = decoder.decompress(remaining, maximum_output - output_size + 1)
            output_size += len(decompressed)
            if output_size > maximum_output:
                raise SmokeError("PNG inflated data exceeds safe limit")
            raster.extend(decompressed)
            remaining = decoder.unconsumed_tail
            if decoder.eof:
                if remaining or decoder.unused_data:
                    raise SmokeError("PNG has data after compressed stream")
                break
    if not decoder.eof or decoder.unused_data:
        raise SmokeError("PNG IDAT zlib stream incomplete")
    if len(raster) != (row_bytes + 1) * height:
        raise SmokeError("PNG lacks the expected decoded scanlines")
    if any(raster[row * (row_bytes + 1)] > 4 for row in range(height)):
        raise SmokeError("PNG scanline uses an invalid filter")
    return {"width": width, "height": height, "bytes": len(data)}


def validate_report(data: object, *, screenshot: bool = False,
                    interactive: bool = False,
                    screenshot_path: Path | None = None) -> dict[str, dict[str, object]]:
    """Evidence-based checks. Missing cardCount is UNVERIFIED and fails gate."""
    if not isinstance(data, dict):
        raise SmokeError("diagnostics must be a JSON object")
    checks: dict[str, dict[str, object]] = {}

    def check(label: str, ok: bool, evidence: object, note: str = "") -> None:
        checks[label] = {"status": "PASS" if ok else "FAIL", "evidence": evidence}
        if note:
            checks[label]["note"] = note

    port = data.get("port")
    url = data.get("url")
    # Interactive navigation leaves WebView on index.html after a verified
    # round trip. Accept this path only for that protocol, never arbitrary URLs.
    expected_paths = ("/", "/index.html") if interactive else ("/",)
    check("loopback", _safe_int(port, 1, 65535) and isinstance(url, str)
          and url in {f"http://127.0.0.1:{port}{path}" for path in expected_paths}, url)
    check("dom_ready", data.get("readyState") == "complete", data.get("readyState"))
    check("root_mount", _safe_int(data.get("rootLength"), 200, 3_000_000),
          data.get("rootLength"))
    body = data.get("bodyTextStart")
    check("body_text", isinstance(body, str) and bool(body.strip()) and "مدار" in body,
          body[:80] if isinstance(body, str) else body)
    check("native_bridge", data.get("bridgeType") == "object"
          and data.get("pywebviewType") == "object", {
              "madar": data.get("bridgeType"), "pywebview": data.get("pywebviewType"),
          })
    check("font_loaded", data.get("fontLoaded") is True, data.get("fontLoaded"))
    check("board_columns", _safe_int(data.get("stageCount"), 1, 100),
          data.get("stageCount"))
    card = data.get("cardCount")
    if card is None:
        checks["visible_cards"] = {
            "status": "UNVERIFIED", "evidence": None,
            "note": "Native QA report lacks cardCount. Add JS diagnostic document.querySelectorAll('.task-card').length.",
        }
    else:
        check("visible_cards", _safe_int(card, 1, 50_000), card)
    if interactive:
        flow = data.get("uiFlow")
        for name in INTERACTIVE_REQUIRED:
            item = flow.get(name) if isinstance(flow, dict) else None
            # The host owns the observations: a JSON object with just
            # {"pass":true} or {"observed":false} cannot green-light release.
            observed = (type(item.get("observed")) is int and
                        item["observed"] == 1) if (
                            isinstance(item, dict) and name == "task_saved_to_host"
                        ) else (isinstance(item, dict) and item.get("observed") is True)
            check("interactive_" + name,
                  isinstance(item, dict) and item.get("pass") is True and observed,
                  item)

    if screenshot:
        result = data.get("screenshot")
        native_done = isinstance(result, dict) and result.get("done") is True
        checked = None
        reason = ""
        try:
            if not screenshot_path:
                raise SmokeError("PNG screenshot path not provided")
            checked = verify_png_complete(screenshot_path)
        except (SmokeError, OSError, zlib.error) as exc:
            reason = f"Cannot verify complete screenshot PNG: {exc}"
        # Validated PNG takes precedence over the native async callback flag;
        # persist the mismatch as a warning for upstream QA-hook diagnosis.
        checks["screenshot"] = {
            "status": "PASS" if checked else "FAIL",
            "evidence": {"native_done": native_done, "verified_png": checked},
        }
        if checked and not native_done:
            checks["screenshot"]["note"] = (
                "Native screenshot.done=false but complete CRC-validated PNG "
                "and zlib stream were independently verified"
            )
        if reason:
            checks["screenshot"]["note"] = reason
    return checks


def _parse_report(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    if not 2 <= path.stat().st_size <= MAX_REPORT_BYTES:
        raise SmokeError("diagnostic report empty or over size limit")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None  # transient write; check again while process is alive
    if not isinstance(value, dict):
        raise SmokeError("diagnostic report must contain JSON object")
    return value


if os.name == "nt":
    import ctypes.wintypes as wt

    class _StartupInfo(ctypes.Structure):
        _fields_ = [
            ("cb", wt.DWORD), ("lpReserved", wt.LPWSTR),
            ("lpDesktop", wt.LPWSTR), ("lpTitle", wt.LPWSTR),
            ("dwX", wt.DWORD), ("dwY", wt.DWORD),
            ("dwXSize", wt.DWORD), ("dwYSize", wt.DWORD),
            ("dwXCountChars", wt.DWORD), ("dwYCountChars", wt.DWORD),
            ("dwFillAttribute", wt.DWORD), ("dwFlags", wt.DWORD),
            ("wShowWindow", wt.WORD), ("cbReserved2", wt.WORD),
            ("lpReserved2", ctypes.POINTER(wt.BYTE)),
            ("hStdInput", wt.HANDLE), ("hStdOutput", wt.HANDLE),
            ("hStdError", wt.HANDLE),
        ]

    class _ProcessInfo(ctypes.Structure):
        _fields_ = [
            ("hProcess", wt.HANDLE), ("hThread", wt.HANDLE),
            ("dwProcessId", wt.DWORD), ("dwThreadId", wt.DWORD),
        ]

    class _BasicLimits(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wt.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wt.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wt.DWORD),
            ("SchedulingClass", wt.DWORD),
        ]

    class _IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class _JobLimits(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BasicLimits),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    class _JobAccounting(ctypes.Structure):
        _fields_ = [
            ("TotalUserTime", ctypes.c_longlong),
            ("TotalKernelTime", ctypes.c_longlong),
            ("ThisPeriodTotalUserTime", ctypes.c_longlong),
            ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
            ("TotalPageFaultCount", wt.DWORD),
            ("TotalProcesses", wt.DWORD),
            ("ActiveProcesses", wt.DWORD),
            ("TotalTerminatedProcesses", wt.DWORD),
        ]


class WindowsOwnedJob:
    """Launch suspended; assign exclusive kill-on-close Job; then resume.

    No PID lookup by executable filename. Fail closed if job ownership cannot
    be established, so a PyInstaller child cannot escape the lifecycle guard.
    """

    def __init__(self, executable: Path, cwd: Path, env: dict[str, str]):
        if os.name != "nt":
            raise SmokeError("Windows GUI smoke requires Windows")
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel = kernel
        self.job = None
        self.process = None
        self.thread = None
        self.pid = None
        self.closed = False
        self.assigned = False
        try:
            self._create(executable, cwd, env)
        except Exception:
            self.stop()
            raise

    def _create(self, executable: Path, cwd: Path, env: dict[str, str]) -> None:
        k = self.kernel
        k.CreateJobObjectW.argtypes = [wt.LPVOID, wt.LPCWSTR]
        k.CreateJobObjectW.restype = wt.HANDLE
        k.SetInformationJobObject.argtypes = [wt.HANDLE, ctypes.c_int, wt.LPVOID, wt.DWORD]
        k.SetInformationJobObject.restype = wt.BOOL
        k.AssignProcessToJobObject.argtypes = [wt.HANDLE, wt.HANDLE]
        k.AssignProcessToJobObject.restype = wt.BOOL
        k.CreateProcessW.argtypes = [
            wt.LPCWSTR, wt.LPWSTR, wt.LPVOID, wt.LPVOID, wt.BOOL, wt.DWORD,
            wt.LPVOID, wt.LPCWSTR, ctypes.POINTER(_StartupInfo),
            ctypes.POINTER(_ProcessInfo),
        ]
        k.CreateProcessW.restype = wt.BOOL
        k.ResumeThread.argtypes = [wt.HANDLE]
        k.ResumeThread.restype = wt.DWORD
        k.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
        k.WaitForSingleObject.restype = wt.DWORD
        k.TerminateJobObject.argtypes = [wt.HANDLE, wt.UINT]
        k.TerminateJobObject.restype = wt.BOOL
        k.CloseHandle.argtypes = [wt.HANDLE]
        k.CloseHandle.restype = wt.BOOL
        k.TerminateProcess.argtypes = [wt.HANDLE, wt.UINT]
        k.TerminateProcess.restype = wt.BOOL
        k.GetExitCodeProcess.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
        k.GetExitCodeProcess.restype = wt.BOOL
        k.QueryInformationJobObject.argtypes = [
            wt.HANDLE, ctypes.c_int, wt.LPVOID, wt.DWORD, wt.LPVOID
        ]
        k.QueryInformationJobObject.restype = wt.BOOL

        self.job = k.CreateJobObjectW(None, None)
        if not self.job:
            raise SmokeError(f"CreateJobObjectW failed: {ctypes.get_last_error()}")
        limits = _JobLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        if not k.SetInformationJobObject(self.job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise SmokeError(f"SetInformationJobObject failed: {ctypes.get_last_error()}")

        si = _StartupInfo()
        si.cb = ctypes.sizeof(si)
        pi = _ProcessInfo()
        # CREATE_SUSPENDED and CREATE_UNICODE_ENVIRONMENT. Assign Job before any
        # executable instruction executes, including PyInstaller child launch.
        flags = 0x00000004 | 0x00000400
        environment = ctypes.create_unicode_buffer(
            "\0".join(f"{key}={value}" for key, value in sorted(env.items(), key=lambda item: item[0].upper()))
            + "\0\0"
        )
        cmdline = ctypes.create_unicode_buffer(f'"{executable}"')
        if not k.CreateProcessW(str(executable), cmdline, None, None, False, flags,
                                ctypes.cast(environment, wt.LPVOID), str(cwd),
                                ctypes.byref(si), ctypes.byref(pi)):
            raise SmokeError(f"CreateProcessW failed: {ctypes.get_last_error()}")
        self.process, self.thread, self.pid = pi.hProcess, pi.hThread, pi.dwProcessId
        if not k.AssignProcessToJobObject(self.job, self.process):
            raise SmokeError(f"AssignProcessToJobObject failed: {ctypes.get_last_error()}")
        self.assigned = True
        if k.ResumeThread(self.thread) == 0xFFFFFFFF:
            raise SmokeError(f"ResumeThread failed: {ctypes.get_last_error()}")

    def poll(self) -> int | None:
        if self.closed or not self.process:
            return None
        k = self.kernel
        status = k.WaitForSingleObject(self.process, 0)
        if status == 0x102:  # WAIT_TIMEOUT
            return None
        if status != 0:
            raise SmokeError("Windows process wait failed")
        result = wintypes.DWORD()
        if not k.GetExitCodeProcess(self.process, ctypes.byref(result)):
            raise SmokeError("Windows process exit status unavailable")
        return int(result.value)

    def stop(self) -> None:
        if self.closed:
            return
        self.closed = True
        k = self.kernel
        try:
            if self.job:
                k.TerminateJobObject(self.job, 0)
            if self.process and not self.assigned:
                # Launch failed before Job assignment. Its suspended process
                # belongs to us; terminate that exact process handle.
                k.TerminateProcess(self.process, 1)
            if self.process:
                k.WaitForSingleObject(self.process, 5000)
            if self.job and self.assigned:
                # PyInstaller onefile starts a child EXE. Wait for *all*
                # processes confined to the owned Job before deleting their
                # extracted DLLs. No system-wide process query/kill is used.
                until = time.monotonic() + 12.0
                while time.monotonic() < until:
                    info = _JobAccounting()
                    if not k.QueryInformationJobObject(
                        self.job, 1, ctypes.byref(info), ctypes.sizeof(info), None
                    ):
                        break
                    if info.ActiveProcesses == 0:
                        break
                    time.sleep(0.1)
        finally:
            for handle in (self.thread, self.process, self.job):
                if handle:
                    k.CloseHandle(handle)
            self.thread = self.process = self.job = None


def _safe_output_parent(parent: Path) -> Path:
    resolved = parent.resolve()
    for envkey in ("APPDATA", "LOCALAPPDATA"):
        sensitive = os.environ.get(envkey)
        if sensitive and (resolved == Path(sensitive).resolve()
                          or resolved.is_relative_to(Path(sensitive).resolve())):
            raise SmokeError("output-dir must not be inside real APPDATA/LOCALAPPDATA")
    if resolved == (PROJECT / "release").resolve() or resolved.is_relative_to((PROJECT / "release").resolve()):
        raise SmokeError("output-dir must not modify release artifacts")
    if not resolved.is_dir():
        raise SmokeError("output-dir must already exist")
    return resolved


@contextmanager
def _disposable_root():
    """Delete only our newly created directory, retrying transient DLL locks."""
    folder = Path(tempfile.mkdtemp(prefix=".qa-v1-gui-isolated-", dir=PROJECT))
    try:
        yield folder
    finally:
        last_error = None
        for retry in range(16):
            try:
                shutil.rmtree(folder)
                last_error = None
                break
            except FileNotFoundError:
                last_error = None
                break
            except (OSError, PermissionError) as exc:
                last_error = exc
                if retry < 15:
                    time.sleep(0.5)
        if last_error is not None:
            raise SmokeError(f"isolated scratch cleanup failed for {folder}: {last_error}")


def run_smoke(executable: Path, *, timeout: float = 75.0, screenshot: bool = False,
              interactive: bool = False,
              output_dir: Path | None = None,
              launcher: Callable[..., Any] = WindowsOwnedJob,
              base_env: dict[str, str] | None = None,
              release_root: Path | None = None) -> dict[str, object]:
    """Single launch, bounded report wait, guaranteed owned-process cleanup."""
    if not 8 <= timeout <= 180:
        raise SmokeError("timeout must be between 8 and 180 seconds")
    target = safe_exe_path(executable, release_root=release_root)
    parent = _safe_output_parent(output_dir) if output_dir is not None else None
    # Place disposable QA state in the project root. On Windows the system
    # temp location is commonly a child of the real LOCALAPPDATA profile.
    with _disposable_root() as scratch:
        env = isolated_environment(base_env if base_env is not None else os.environ,
                                   scratch, screenshot=screenshot, interactive=interactive)
        diagnostics = scratch / "diagnostics.json"
        screenshot_path = scratch / "screenshot.png"
        job = None
        observed: dict[str, Any] | None = None
        early_exit: int | None = None
        started = time.monotonic()
        try:
            job = launcher(target, PROJECT, env)
            while time.monotonic() - started < timeout:
                observed = _parse_report(diagnostics)
                if observed is not None:
                    break
                early_exit = job.poll()
                if early_exit is not None:
                    # It may have written the report at the instant of exit.
                    observed = _parse_report(diagnostics)
                    break
                time.sleep(0.2)
        finally:
            if job is not None:
                job.stop()  # Stops only processes in the Job created by us.

        if observed is None:
            reason = (f"EXE exited before report (code {early_exit})"
                      if early_exit is not None else f"no report within {timeout:g} seconds")
            return {"status": "FAIL", "reason": reason, "checks": {}, "pid": getattr(job, "pid", None)}

        checks = validate_report(observed, screenshot=screenshot, interactive=interactive,
                                 screenshot_path=screenshot_path)
        passed = all(item["status"] == "PASS" for item in checks.values())
        result: dict[str, object] = {
            "status": "PASS" if passed else "FAIL",
            "checks": checks,
            "pid": getattr(job, "pid", None),
            "report": "captured",
            "screenshot": "requested" if screenshot else "not_requested",
        }
        if parent is not None:
            destination = Path(tempfile.mkdtemp(prefix="v1-gui-smoke-", dir=parent))
            shutil.copyfile(diagnostics, destination / "diagnostics.json")
            if screenshot_path.is_file() and screenshot_path.stat().st_size <= MAX_SCREENSHOT_BYTES:
                shutil.copyfile(screenshot_path, destination / "screenshot.png")
            result["artifacts"] = str(destination)
        return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Isolated Windows EXE GUI QA, RC1")
    parser.add_argument("--exe", type=Path, default=DEFAULT_EXE,
                        help="EXE path within this project's release directory")
    parser.add_argument("--timeout", type=float, default=75,
                        help="seconds to wait for native MADAR_QA_REPORT (8-180)")
    parser.add_argument("--screenshot", action="store_true",
                        help="request screenshot via existing native MADAR_QA_SCREENSHOT")
    parser.add_argument("--interactive", action="store_true",
                        help="exercise independent /accounting.html, verify rial ledger and create one synthetic task in isolated QA AppData")
    parser.add_argument("--output-dir", type=Path,
                        help="existing NON-APPDATA directory to retain QA report/screenshot")
    args = parser.parse_args(argv)
    if os.name != "nt":
        print(json.dumps({"status": "UNSUPPORTED", "reason": "Windows GUI required"}))
        return EXIT_UNSUPPORTED
    try:
        safe_exe_path(args.exe)
    except FileNotFoundError as exc:
        print(json.dumps({"status": "NOT_RUN", "reason": str(exc)}, ensure_ascii=True))
        return EXIT_MISSING
    except SmokeError as exc:
        print(json.dumps({"status": "FAIL", "reason": str(exc)}, ensure_ascii=True))
        return EXIT_FAIL
    try:
        result = run_smoke(args.exe, timeout=args.timeout, screenshot=args.screenshot,
                           interactive=args.interactive,
                           output_dir=args.output_dir)
    except (SmokeError, OSError, ValueError) as exc:
        print(json.dumps({"status": "FAIL", "reason": str(exc)}, ensure_ascii=True))
        return EXIT_FAIL
    # The default Windows console code page may be cp1256 or cp1252 rather
    # than UTF-8. JSON ASCII escaping avoids a UnicodeEncodeError *after*
    # successful GUI diagnostics and process cleanup.
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return EXIT_PASS if result["status"] == "PASS" else EXIT_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
