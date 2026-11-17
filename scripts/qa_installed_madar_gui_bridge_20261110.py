"""Isolated installed Madar 1.0.26 GUI smoke and opt-in manual-send QA.

This launches one SHA-pinned EXE with all profile/cache/temporary paths mapped
to a disposable directory, reads its built-in QA report, then closes ONLY the
process subtree created by this invocation. The --send-isolated-ui mode toggles
consent and clicks one synthetic saved-card button through GUI accessibility;
default mode is observation-only. No Taraz EXE, ledger or LAN host is opened.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import ctypes
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from types import MappingProxyType
from unittest.mock import patch


EXPECTED = "9bb1471944fc4b31aece7470e9d433fb68e207653d865ca3881c8d5654c943a4"
_PROPOSAL_ID = re.compile(r"[0-9a-f]{32}\Z")


@contextmanager
def _disposable_gui_qa_directory():
    """Own one QA temp root and retry transient WebView2 file-handle cleanup.

    Even after the spawned GUI exits, WebView2/BrowserMetrics may briefly keep
    a handle open on Windows. Never ignore a persistent cleanup failure, never
    address any other directory, and never touch user GUI processes.
    """
    owned = tempfile.TemporaryDirectory(prefix="madar-qa-taraz-bridge-ui-")
    try:
        yield owned.name
    finally:
        root = Path(owned.name)
        if (not root.is_absolute() or
                not root.name.startswith("madar-qa-taraz-bridge-ui-") or
                root.is_symlink() or getattr(root, "is_junction", lambda: False)()):
            raise PermissionError("Refusing cleanup outside owned QA temporary directory")
        for attempt in range(20):
            try:
                owned.cleanup()
                break
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(0.25)


def _visible_owned_qa_windows_once(pid: int) -> list[tuple[int, int]]:
    """Take one Win32 window snapshot for the QA PID and its descendants only."""
    user32 = ctypes.windll.user32
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    allowed = {pid}
    try:
        import psutil
        allowed.update(child.pid for child in psutil.Process(pid).children(recursive=True))
    except (ImportError, OSError):
        pass
    owned = []

    class _Rect(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    def enum_window(hwnd, _):
        observed = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(observed))
        if observed.value in allowed and user32.IsWindowVisible(hwnd):
            rect = _Rect()
            if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                width, height = rect.right - rect.left, rect.bottom - rect.top
                if width >= 350 and height >= 250:
                    owned.append((width * height, int(hwnd)))
        return True

    user32.EnumWindows(callback_type(enum_window), 0)
    return owned


def _owned_qa_hwnd(pid: int, *, wait_seconds: float = 10.0,
                   poll_seconds: float = 0.25) -> int:
    """Wait briefly for one *owned* visible GUI window, then fail closed.

    The installed EXE can write its diagnostic JSON before WebView2's native
    window is visible. Never fall back to window title, desktop focus, an
    existing Madar process or an unrelated PID. A second owned window must
    disappear before we can select any HWND.
    """
    if (os.name != "nt" or type(pid) is not int or pid <= 0 or
            not 0 <= wait_seconds <= 20 or not 0 < poll_seconds <= 2):
        raise ValueError("Bounded Windows QA PID/window wait required")
    try:
        import psutil
    except ImportError as exc:
        raise RuntimeError("Cannot verify own QA process identity") from exc
    try:
        launched = psutil.Process(pid)
        original_creation_time = launched.create_time()
    except (OSError, psutil.Error) as exc:
        raise RuntimeError("Cannot verify own QA process identity") from exc
    deadline = time.monotonic() + wait_seconds
    last_count = 0
    while True:
        try:
            if (not launched.is_running() or
                    launched.create_time() != original_creation_time):
                raise RuntimeError("QA process exited/reused while waiting for its GUI")
        except psutil.Error as exc:
            raise RuntimeError("QA process disappeared while waiting for its GUI") from exc
        owned = _visible_owned_qa_windows_once(pid)
        last_count = len(owned)
        if last_count == 1:
            return owned[0][1]
        now = time.monotonic()
        if now >= deadline:
            if last_count == 0:
                raise RuntimeError("No large visible QA-owned native window after bounded wait")
            raise RuntimeError("Ambiguous QA-owned windows after bounded wait; refusing UI operation")
        time.sleep(min(poll_seconds, deadline - now))


def _run_owned_uia(pid: int, script: str, *, timeout: int = 25) -> dict:
    hwnd = _owned_qa_hwnd(pid)
    script = script.replace("__HWND__", str(hwnd))
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        text=True, capture_output=True, timeout=timeout, check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if completed.returncode:
        raise RuntimeError("QA UI automation failed closed: " + completed.stderr[-900:])
    observed = json.loads(completed.stdout.strip())
    if not isinstance(observed, dict):
        raise RuntimeError("QA UI automation returned invalid metadata")
    return observed


def _probe_own_gui(pid: int) -> dict:
    """Read Windows UI Automation on this QA process's window, never user windows."""
    script = r'''
$ErrorActionPreference='Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$own = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]__HWND__)
if ($null -eq $own) { throw 'QA-owned window inaccessible' }
$scope = [System.Windows.Automation.TreeScope]::Descendants
$condition = [System.Windows.Automation.Condition]::TrueCondition
function FindQaNodes($window) {
    $nodes = $window.FindAll($scope, $condition)
    $taraz = @($nodes | Where-Object {
        $_.Current.Name.Trim() -eq 'ارسال به تراز' -and
        $_.Current.ControlType -eq [System.Windows.Automation.ControlType]::Button -and
        -not $_.Current.IsOffscreen -and $_.Current.BoundingRectangle.Width -gt 5
    })
    $settings = @($nodes | Where-Object { $_.Current.Name -eq 'تنظیمات مدار' -and $_.Current.ControlType -eq [System.Windows.Automation.ControlType]::Button })
    $close = @($nodes | Where-Object { $_.Current.Name -eq 'بستن' -and $_.Current.ControlType -eq [System.Windows.Automation.ControlType]::Button })
    $connection = @($nodes | Where-Object { $_.Current.Name -eq 'اتصال تراز' })
    $consent = @($nodes | Where-Object { $_.Current.Name -like '*اجازهٔ ارسال دستی پیشنهاد از کارت به تراز*' })
    return @{ taraz=$taraz; count=$nodes.Count; settings=$settings; close=$close; connection=$connection; consent=$consent }
}
$snapshot = FindQaNodes $own
$after = $snapshot
for ($retry=0; $retry -lt 14 -and $after.taraz.Count -eq 0; $retry++) {
    Start-Sleep -Milliseconds 250
    $after = FindQaNodes $own
}
[pscustomobject]@{
    qaWindowFound=$true
    tarazButtonAccessibleAfter=$after.taraz.Count -ge 1
    tarazButtonAccessibleBefore=$snapshot.taraz.Count -ge 1
    tarazButtonEnabled=$after.taraz.Count -ge 1 -and $after.taraz[0].Current.IsEnabled
    settingsButtonCount=$after.settings.Count
    closeButtonCount=$after.close.Count
    connectionControlCount=$after.connection.Count
    consentControlCount=$after.consent.Count
    appearedAfterReport=($snapshot.taraz.Count -eq 0 -and $after.taraz.Count -ge 1)
    accessibilityElementCount=$after.count
} | ConvertTo-Json -Compress
'''
    return _run_owned_uia(pid, script, timeout=20)


def _inspect_navigation(pid: int) -> dict:
    """Close the synthetic drawer then inventory semantic QA controls."""
    script = r'''
$ErrorActionPreference='Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]__HWND__)
if ($null -eq $root) { throw 'QA window missing' }
$scope=[System.Windows.Automation.TreeScope]::Descendants
$all=[System.Windows.Automation.Condition]::TrueCondition
function Nodes { return $root.FindAll($scope,$all) }
$nodes=Nodes
$close=@($nodes | Where-Object { $_.Current.Name -eq 'بستن' -and $_.Current.ControlType -eq [System.Windows.Automation.ControlType]::Button -and $_.Current.IsEnabled -and -not $_.Current.IsOffscreen })
if($close.Count -ne 1) { throw "QA drawer close selector not unique: $($close.Count)" }
$close[0].GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
Start-Sleep -Milliseconds 650
$nodes=Nodes
$cardButtons=@($nodes | Where-Object { $_.Current.ControlType -eq [System.Windows.Automation.ControlType]::Button -and $_.Current.IsEnabled -and -not $_.Current.IsOffscreen -and $_.Current.Name -like 'جزئیات*' })
$allAccessibleCards=@($nodes | Where-Object { $_.Current.Name -like 'جزئیات*' -and $_.Current.BoundingRectangle.Width -gt 10 })
$settings=@($nodes | Where-Object { $_.Current.Name -eq 'تنظیمات مدار' -and $_.Current.ControlType -eq [System.Windows.Automation.ControlType]::Button -and $_.Current.IsEnabled -and -not $_.Current.IsOffscreen })
[pscustomobject]@{drawerClosed=$true;settingsButtonCount=$settings.Count;cardButtonCount=$cardButtons.Count;cardAccessibleCount=$allAccessibleCards.Count;cardRoles=@($allAccessibleCards | ForEach-Object { $_.Current.ControlType.ProgrammaticName });firstCardButtonNameLength=if($cardButtons.Count){$cardButtons[0].Current.Name.Length}else{0}} | ConvertTo-Json -Compress
'''
    return _run_owned_uia(pid, script)


def _ui_send_once(pid: int, expected_title: str) -> dict:
    """Invoke consent and one send button through this QA EXE's own UIA tree.

    No backend substitute, JS evaluation, debug port, direct file creation,
    foreground coordinate click, network request or Taraz process involved.
    Every control is scoped to a Win32 HWND owned by the launched QA PID.
    """
    if not expected_title or len(expected_title) > 300:
        raise ValueError("Synthetic target title missing/oversized")
    card_label = "جزئیات " + expected_title
    label_b64 = base64.b64encode(card_label.encode("utf-8")).decode("ascii")
    script = r'''
$ErrorActionPreference='Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]__HWND__)
if ($null -eq $root) { throw 'QA_WINDOW_NOT_FOUND' }
$scope = [System.Windows.Automation.TreeScope]::Descendants
$condition = [System.Windows.Automation.Condition]::TrueCondition
$button = [System.Windows.Automation.ControlType]::Button
$checkbox = [System.Windows.Automation.ControlType]::CheckBox
$invokePattern = [System.Windows.Automation.InvokePattern]::Pattern
$togglePattern = [System.Windows.Automation.TogglePattern]::Pattern
$cardName = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__CARD__'))
function Nodes { return $root.FindAll($scope,$condition) }
function Button($exactName) {
    return @((Nodes) | Where-Object {
        $_.Current.ControlType -eq $button -and $_.Current.Name -eq $exactName -and
        $_.Current.IsEnabled -and -not $_.Current.IsOffscreen -and
        $_.Current.BoundingRectangle.Width -gt 5
    })
}
function InvokeUnique($exactName, $gate) {
    $matches = @(Button $exactName)
    if ($matches.Count -ne 1) { throw "$gate : expected one enabled visible button; found $($matches.Count)" }
    $matches[0].GetCurrentPattern($invokePattern).Invoke()
}
function WaitButton($name) {
    for($i=0; $i -lt 24; $i++){
        $matches=@(Button $name)
        if($matches.Count -eq 1){return $matches[0]}
        if($matches.Count -gt 1){throw "AMBIGUOUS_BUTTON $name"}
        Start-Sleep -Milliseconds 250
    }
    throw "BUTTON_NOT_READY $name"
}
# The shipped QA hook has opened a *synthetic* drawer. Close it through UIA,
# never invoke underlying controls while a modal is over them.
$sendBefore = @(Button 'ارسال به تراز')
if ($sendBefore.Count -ne 0) { throw 'SEND_ENABLED_BEFORE_CONSENT' }
InvokeUnique 'بستن' 'CLOSE_CARD'
Start-Sleep -Milliseconds 350
if (@(Button 'ارسال به تراز').Count -ne 0) { throw 'CARD_DRAWER_NOT_CLOSED' }
InvokeUnique 'تنظیمات مدار' 'OPEN_SETTINGS'
Start-Sleep -Milliseconds 350
InvokeUnique 'اتصال تراز' 'OPEN_TARAZ_SETTINGS'
Start-Sleep -Milliseconds 350
$found = @((Nodes) | Where-Object {
    $_.Current.ControlType -eq $checkbox -and
    $_.Current.Name -like '*اجازهٔ ارسال دستی پیشنهاد از کارت به تراز*' -and
    -not $_.Current.IsOffscreen -and $_.Current.IsEnabled
})
if ($found.Count -ne 1) { throw "CONSENT_CHECKBOX_SELECTOR: found $($found.Count)" }
$consentPattern = $found[0].GetCurrentPattern($togglePattern)
$consentBefore = $consentPattern.Current.ToggleState.ToString()
if($consentBefore -ne 'Off'){throw "CONSENT_NOT_DEFAULT_OFF $consentBefore"}
$consentPattern.Toggle()
$consentOn=$false
for($i=0;$i -lt 16;$i++) {
    Start-Sleep -Milliseconds 150
    $found = @((Nodes) | Where-Object {
        $_.Current.ControlType -eq $checkbox -and
        $_.Current.Name -like '*اجازهٔ ارسال دستی پیشنهاد از کارت به تراز*' -and
        -not $_.Current.IsOffscreen
    })
    if($found.Count -ne 1) { throw "CONSENT_DISAPPEARED: found $($found.Count)" }
    $consentPattern=$found[0].GetCurrentPattern($togglePattern)
    if($consentPattern.Current.ToggleState.ToString() -eq 'On') {$consentOn=$true;break}
}
if(-not $consentOn){throw 'CONSENT_DID_NOT_TOGGLE'}
InvokeUnique 'بستن' 'CLOSE_SETTINGS'
Start-Sleep -Milliseconds 350
$card = WaitButton $cardName
$card.GetCurrentPattern($invokePattern).Invoke()
$send = WaitButton 'ارسال به تراز'
if(-not $send.Current.IsEnabled) { throw 'SEND_DISABLED_AFTER_CONSENT' }
# Exactly one explicit manual QA button invocation. Never retry a send.
$send.GetCurrentPattern($invokePattern).Invoke()
[pscustomobject]@{
    verifiedQaWindow=$true
    consentBefore=$consentBefore
    consentAfter='On'
    targetCardReopenedThroughUi=$true
    sendButtonWasEnabled=$true
    manualSendInvocations=1
    backendCalledDirectly=$false
} | ConvertTo-Json -Compress
'''.replace("__CARD__", label_b64)
    return _run_owned_uia(pid, script, timeout=35)


def _read_one_disposable_pending(local_appdata: Path, task: dict) -> dict:
    """Read-back of exactly one schema-1 proposal created by installed UI."""
    local_appdata = local_appdata.resolve(strict=True)
    sandbox = local_appdata.parent.parent
    if (not sandbox.name.startswith("madar-qa-taraz-bridge-ui-") or
            local_appdata != sandbox / "AppData" / "Local"):
        raise PermissionError("Refusing proposal read outside disposable GUI QA profile")
    bridge = local_appdata / "Madar-Taraz-Bridge"
    pending = bridge / "pending"
    if bridge.is_symlink() or not pending.is_dir() or pending.is_symlink():
        raise AssertionError("Disposable proposal pending directory not created")
    files = list(pending.iterdir())
    if len(files) != 1 or files[0].suffix != ".json" or files[0].is_symlink():
        raise AssertionError(f"Expected one disposable pending proposal, saw {len(files)} entries")
    file = files[0]
    if not 100 <= file.stat().st_size <= 32768:
        raise AssertionError("Disposable schema-1 proposal is empty or oversized")
    def unique_fields(pairs):
        record = {}
        for key, value in pairs:
            if key in record:
                raise ValueError("Duplicate proposal JSON field")
            record[key] = value
        return record

    data = json.loads(file.read_text(encoding="utf-8"),
                      object_pairs_hook=unique_fields)
    required = {"schema", "source", "id", "taskId", "title", "projectId", "createdUtc"}
    if not isinstance(data, dict) or set(data) != required:
        raise AssertionError("Unexpected schema-1 proposal fields")
    if (type(data["schema"]) is not int or data["schema"] != 1 or
            data["source"] != "madar" or
            type(data["id"]) is not str or not _PROPOSAL_ID.fullmatch(data["id"]) or
            file.name != data["id"] + ".json" or
            data["taskId"] != task["id"] or
            data["title"] != task["title"].strip() or
            data["projectId"] != task["projectId"] or
            not isinstance(data["createdUtc"], str) or "T" not in data["createdUtc"]):
        raise AssertionError("Malformed schema-1 proposal or unexpected synthetic target")
    try:
        timestamp = datetime.fromisoformat(data["createdUtc"])
    except ValueError as exc:
        raise AssertionError("Invalid proposal UTC timestamp") from exc
    if timestamp.utcoffset() != timedelta(0):
        raise AssertionError("Proposal timestamp missing explicit UTC offset")
    reviewed = bridge / "reviewed"
    if reviewed.exists() and (reviewed.is_symlink() or any(reviewed.iterdir())):
        raise AssertionError("Unexpected reviewed/financial output in disposable bridge")
    return {
        "pendingProposalCount": 1, "schema": data["schema"],
        "source": data["source"], "syntheticTaskIdMatched": True,
        "syntheticProjectIdMatched": True, "syntheticTitleMatched": True,
        "proposalIdWellFormed": True, "proposalFilenameMatched": True,
        "containsExpenseOrLedger": False,
    }


def _notify_disposable_proposal_ready(callback, *, sandbox_root: Path,
                                      bridge_root: Path, verified: dict,
                                      expected_task: dict):
    """Offer the actual GUI-created proposal to a caller before QA teardown.

    Callback positional arguments are ONLY (exact disposable bridge Path,
    immutable 32-hex proposal ID, read-only synthetic task metadata mapping).
    The caller owns callback behavior; this function supplies no real paths or
    credentials and never invokes Taraz, a backend or a network operation.
    The return value is exposed only when an explicit callback was supplied.
    """
    if not callable(callback):
        raise TypeError("on_disposable_proposal_ready must be callable")
    if not isinstance(verified, dict) or any((
        verified.get("pendingProposalCount") != 1,
        verified.get("schema") != 1,
        verified.get("source") != "madar",
        verified.get("syntheticTaskIdMatched") is not True,
        verified.get("syntheticProjectIdMatched") is not True,
        verified.get("syntheticTitleMatched") is not True,
        verified.get("proposalIdWellFormed") is not True,
        verified.get("proposalFilenameMatched") is not True,
        verified.get("containsExpenseOrLedger") is not False,
    )):
        raise AssertionError("Cannot call Taraz reviewer without validated proposal")
    if not isinstance(sandbox_root, Path) or not isinstance(bridge_root, Path):
        raise TypeError("Callback paths must be concrete Path values")
    # Distinguish the deliberately created TemporaryDirectory from a matching
    # name supplied by a caller. Every component must resolve to that exact
    # temporary root; symlinks/junctions may not escape the disposable tree.
    root = sandbox_root.absolute()
    if (not root.is_dir() or not root.name.startswith("madar-qa-taraz-bridge-ui-") or
            root.is_symlink() or root.is_junction() or root.resolve(strict=True) != root):
        raise PermissionError("Callback requires original disposable QA root")
    local = root / "AppData" / "Local"
    expected_bridge = local / "Madar-Taraz-Bridge"
    if bridge_root.absolute() != expected_bridge:
        raise PermissionError("Callback bridge root is outside exact disposable path")
    for directory in (root / "AppData", local, bridge_root, bridge_root / "pending"):
        if (not directory.is_dir() or directory.is_symlink() or
                directory.is_junction() or directory.resolve(strict=True) != directory):
            raise PermissionError("Callback bridge has an unsafe/missing component")
    pending = bridge_root / "pending"
    files = list(pending.iterdir())
    if (len(files) != 1 or not files[0].is_file() or
            files[0].is_symlink() or files[0].is_junction()):
        raise AssertionError("Callback requires exactly one real proposal file")
    identifier = files[0].stem
    if not _PROPOSAL_ID.fullmatch(identifier) or files[0].name != identifier + ".json":
        raise AssertionError("Callback proposal identifier/filename mismatch")
    if not isinstance(expected_task, dict) or any(
            not isinstance(expected_task.get(key), str) or
            not expected_task[key].strip()
            for key in ("id", "projectId", "title")):
        raise AssertionError("Callback expects validated synthetic card metadata")
    task_metadata = MappingProxyType({
        "id": expected_task["id"],
        "projectId": expected_task["projectId"],
        "title": expected_task["title"],
    })
    return callback(expected_bridge, identifier, task_metadata)


def _close_own_window(pid: int):
    user32 = ctypes.windll.user32
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    allowed = {pid}
    try:
        import psutil
        allowed.update(p.pid for p in psutil.Process(pid).children(recursive=True))
    except (ImportError, OSError):
        pass

    def callback(hwnd, extra):
        observed = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(observed))
        if observed.value in allowed:
            user32.PostMessageW(hwnd, 0x0010, 0, 0)
        return True

    user32.EnumWindows(callback_type(callback), 0)


def run(*, inspect_navigation: bool = False, send_once_ui: bool = False,
        on_disposable_proposal_ready=None):
    """Run SHA-pinned EXE QA; optional callback sees only a verified QA inbox.

    The callback is allowed only with send_once_ui=True, after manual UI
    submission and schema-1 readback, while the TemporaryDirectory still exists.
    It receives (bridge_root: Path, proposal_id: str, expected_task: mapping).
    When absent, existing CLI output and cleanup behavior are unchanged. When
    supplied, the callback's return value is included as `tarazCycle`.
    """
    if inspect_navigation and send_once_ui:
        raise ValueError("Cannot inspect navigation and send in the same QA run")
    if on_disposable_proposal_ready is not None:
        if not send_once_ui:
            raise ValueError("Callback requires send_once_ui=True")
        if not callable(on_disposable_proposal_ready):
            raise TypeError("on_disposable_proposal_ready must be callable")
    local = os.environ.get("LOCALAPPDATA")
    if os.name != "nt" or not local:
        raise RuntimeError("Windows user LOCALAPPDATA required")
    executable = (Path(local) / "Programs/MadarDesk/versions/1.0.26/Madar-Desk.exe")
    if not executable.is_file() or executable.is_symlink():
        raise PermissionError("Expected installed Madar executable missing/unsafe")
    if hashlib.sha256(executable.read_bytes()).hexdigest() != EXPECTED:
        raise PermissionError("Installed executable changed since review")

    with _disposable_gui_qa_directory() as path:
        root = Path(path)
        env = os.environ.copy()
        for name, rel in {
            "APPDATA": "AppData/Roaming", "LOCALAPPDATA": "AppData/Local",
            "TEMP": "Temp", "TMP": "Temp", "WEBVIEW2_USER_DATA_FOLDER": "WebView2",
        }.items():
            folder = root / rel
            folder.mkdir(parents=True, exist_ok=True)
            env[name] = str(folder)
        for name in list(env):
            if name.startswith("MADAR_QA_"):
                env.pop(name)
        env["MADAR_QA_REPORT"] = str(root / "gui-report.json")
        env["MADAR_QA_VIEW"] = "task-detail"
        env["MADAR_RELEASE_QA"] = "1"
        env.pop("MADAR_QA_INTERACTION", None)
        # Make WebView2's actual semantic UI visible to Windows UI Automation.
        # No debug port or external automation endpoint is opened.
        env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = "--force-renderer-accessibility"
        for name in ("HOME", "USERPROFILE"):
            env[name] = str(root)
        report_path = Path(env["MADAR_QA_REPORT"])

        # Explicit synthetic fixture for the packaged task-editor QA view;
        # the installed EXE is never pointed at a real user data directory.
        source_root = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(source_root))
        try:
            with patch.dict(os.environ, {key: env[key] for key in (
                    "APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "USERPROFILE", "HOME")}):
                from native_app import atomic_save, initial_state
                seed_dir = Path(env["APPDATA"]) / "MadarDesk"
                seed_dir.mkdir(parents=True, exist_ok=False)
                seed = initial_state()
                seed["workspaces"] = [{
                    "id": "workspace-legacy", "name": "Synthetic QA Workspace",
                    "archived": False,
                }]
                seed["boards"] = [{
                    "id": "qa-board", "workspaceId": "workspace-legacy",
                    "projectId": "p-sample", "name": "Synthetic QA Board",
                    "color": "#3d977e", "archived": False,
                    "stages": seed["stages"], "labelDefinitions": [],
                    "customFields": [],
                }]
                for task in seed["tasks"]:
                    if task["projectId"] == "p-sample":
                        task["boardId"] = "qa-board"
                        task["listId"] = task["status"]
                targets = [task for task in seed["tasks"]
                           if task.get("projectId") == "p-sample"]
                if len(targets) != 4 or len({task["title"] for task in targets}) != 4:
                    raise AssertionError("Synthetic QA fixture requires four unique card titles")
                target_card = targets[0]
                atomic_save(seed_dir / "tasks.json", seed)
        finally:
            sys.path.remove(str(source_root))

        process = subprocess.Popen(
            [str(executable)], cwd=str(executable.parent), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                if report_path.is_file() and report_path.stat().st_size > 2:
                    break
                if process.poll() is not None:
                    raise RuntimeError("QA Madar EXE exited before GUI diagnostic")
                time.sleep(0.2)
            if not report_path.is_file():
                raise RuntimeError("QA Madar WebView2 report not produced")
            report = json.loads(report_path.read_text(encoding="utf-8"))
            if not isinstance(report, dict) or report.get("rootLength", 0) < 1000:
                raise AssertionError("QA Madar task UI not mounted")
            if report.get("bridgeType") != "object":
                raise AssertionError("QA Madar JS bridge not mounted")
            if report.get("cardCount") != 4 or report.get("stageCount") != 5:
                raise AssertionError("Expected four isolated cards and five lanes")
            layout = report.get("taskLayout")
            # The packaged hook opens a synthetic card, but its taskLayout
            # Javascript may fail on null `.edit-grid` (which is rendered only
            # in an optional advanced panel). Inspect the actual rendered
            # send button through read-only Windows accessibility instead.
            gui = _probe_own_gui(process.pid)
            if not gui.get("tarazButtonAccessibleAfter"):
                raise AssertionError("Installed GUI card drawer/send-to-Taraz button was not observed")
            if inspect_navigation:
                return {"isolatedInstalledGui": True, "navigation": _inspect_navigation(process.pid)}
            if send_once_ui:
                pending = Path(env["LOCALAPPDATA"]) / "Madar-Taraz-Bridge" / "pending"
                if pending.exists() or pending.is_symlink():
                    raise AssertionError("Disposable pending folder must start absent")
                interaction = _ui_send_once(process.pid, target_card["title"])
                if interaction.get("manualSendInvocations") != 1:
                    raise AssertionError("GUI send invocation count not exactly one")
                for _ in range(48):
                    if pending.is_dir() and any(pending.iterdir()):
                        break
                    if process.poll() is not None:
                        raise RuntimeError("Installed QA EXE exited before proposal publication")
                    time.sleep(0.25)
                proposal = _read_one_disposable_pending(Path(env["LOCALAPPDATA"]), target_card)
                cycle = None
                if on_disposable_proposal_ready is not None:
                    cycle = _notify_disposable_proposal_ready(
                        on_disposable_proposal_ready,
                        sandbox_root=root,
                        bridge_root=Path(env["LOCALAPPDATA"]) / "Madar-Taraz-Bridge",
                        verified=proposal,
                        expected_task=target_card,
                    )
                response = {
                    "isolatedInstalledGui": True,
                    "uiConsentAndManualSend": interaction,
                    "disposableProposal": proposal,
                    "installedExecutableSha256Matched": True,
                    "renderedCardCount": report["cardCount"],
                    "renderedStageCount": report["stageCount"],
                    "realProfileAccessed": False,
                    "realTarazOrLedgerOpened": False,
                }
                if on_disposable_proposal_ready is not None:
                    response["tarazCycle"] = cycle
                return response
            return {
                "installedMadarGuiMounted": True,
                "renderedCardCount": report.get("cardCount"),
                "renderedStageCount": report.get("stageCount"),
                "packagedTaskEditorObserved": isinstance(layout, dict) or gui.get("tarazButtonAccessibleAfter") is True,
                "packagedTaskEditorObservedViaBuiltInHook": isinstance(layout, dict),
                "builtInTaskLayoutDiagnostic": (
                    "object" if isinstance(layout, dict) else
                    "javascript-error" if isinstance(layout, str) else "absent"
                ),
                "builtInTaskLayoutErrorFragment": layout[:230] if isinstance(layout, str) else None,
                "packagedTarazSendButtonObserved": gui.get("tarazButtonAccessibleAfter") is True,
                "packagedTarazSendButtonEnabled": gui.get("tarazButtonEnabled") is True,
                "quickActionButtonCount": layout.get("quickButtons") if isinstance(layout, dict) else None,
                "qaAccessibility": gui,
                "realProfileAccessed": False,
                "tarazOrFinanceAccessed": False,
            }
        finally:
            if process.poll() is None:
                _close_own_window(process.pid)
                try:
                    process.wait(timeout=6)
                except subprocess.TimeoutExpired:
                    subprocess.run(
                        ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        timeout=10, check=False,
                    )
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        raise RuntimeError("QA process did not exit; manual inspection required")


if __name__ == "__main__":
    mode = sys.argv[1:]
    if mode not in ([], ["--inspect-navigation"], ["--send-isolated-ui"]):
        raise SystemExit("Usage: qa_installed_madar_gui_bridge_20261110.py [--inspect-navigation|--send-isolated-ui]")
    print(json.dumps(run(inspect_navigation=mode == ["--inspect-navigation"],
                         send_once_ui=mode == ["--send-isolated-ui"]),
                     ensure_ascii=False, sort_keys=True))
