"""Run the *pinned QA-only* Madar current-source EXE with synthetic GUI state.

No installation, real APPDATA, existing Madar process, Taraz launch, or ledger.
Uses the existing installed-Madar GUI QA's PID-scoped accessibility helpers
read-only; it NEVER calls that module's installed-executable run() function.
"""
from __future__ import annotations

from contextlib import contextmanager
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
EXE = Path(
    r"D:\CoS-Test\MTR-MADAR-TARAZ-QA-BUNDLE-20261110"
    r"\run-20261110-144128-10416-207ce8ba\exe-dist"
    r"\Madar-Taraz-Connection-QA-20261110-NONRELEASE.exe"
)
EXPECTED_SHA256 = "11a9726f976bd633c6eb120b939e1d7aab63c6ca99a3e3b5a5cc57bd967ed4f9"
METHODS = ("tarazIntegrationOpenLocal", "tarazIntegrationPrepare",
           "tarazIntegrationQueue", "tarazIntegrationHistory")
REF = ROOT / "scripts" / "qa_installed_madar_gui_bridge_20261110.py"
BUILD = ROOT / "scripts" / "qa_mtr_connection_build_20261110.py"
DETACHED_TARAZ_REVIEW = Path(
    r"D:\CoS-Test\000- Taraz\taraz-mtr-e2-isolated-20261109\taraz_integration.py"
)


def digest(file: Path) -> str:
    h = hashlib.sha256()
    with file.open("rb") as src:
        for chunk in iter(lambda: src.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_regular_file(file: Path) -> None:
    if (not file.is_file() or file.is_symlink() or
            (hasattr(file, "is_junction") and file.is_junction())):
        raise PermissionError("Missing, symlinked or linked file: " + str(file))


def _load_module(file: Path, name: str):
    safe_regular_file(file)
    spec = importlib.util.spec_from_file_location(name, str(file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_pinned_executable() -> dict:
    """Check frozen artifact, embedded QA proof, and current seeding source."""
    if os.name != "nt":
        raise RuntimeError("Windows required for isolated WebView2 QA")
    safe_regular_file(EXE)
    actual = digest(EXE)
    if actual != EXPECTED_SHA256:
        raise PermissionError("QA EXE SHA-256 pin mismatch; nothing launched")
    run_root = EXE.parent.parent
    proof_file = run_root / "qa-provenance.json"
    ui_files = run_root / "vite-assets-sha256.json"
    for file in (proof_file, ui_files):
        safe_regular_file(file)
    proof = json.loads(proof_file.read_text(encoding="utf-8"))
    manifest = json.loads(ui_files.read_text(encoding="utf-8"))
    if (proof.get("purpose") != "NON_RELEASE_QA" or
            proof.get("notFunctionalTestOrReleaseApproval") is not True):
        raise PermissionError("EXE is not an audited non-release QA build")
    builder = _load_module(BUILD, "mtr_current_qa_archive_verifier")
    archive_result = builder.verify_exe(EXE, proof_file, manifest)
    for name, expected in (("native_app.py", proof.get("nativeSourceSha256")),
                           ("src/App.jsx", proof.get("uiSourceSha256"))):
        source = ROOT / name
        safe_regular_file(source)
        if digest(source) != expected:
            raise PermissionError("Current seed source drift: " + name)
    for name in METHODS:
        if name not in archive_result["compiledBridgeMethods"]:
            raise PermissionError("Compiled Bridge method missing: " + name)
    return {
        "pinnedSha256": actual,
        "exeBytes": EXE.stat().st_size,
        "archiveBridgeMethods": archive_result["compiledBridgeMethods"],
        "embeddedViteAssetsShaVerified": archive_result["embeddedViteAssetsVerified"],
        "embeddedProvenanceShaVerified": archive_result["embeddedProvenanceMatches"],
        "sourceSnapshotTreeSha256": proof["sourceSnapshotTreeSha256"],
    }


def _baseline_installed_processes() -> dict:
    import psutil
    results = {}
    for process in psutil.process_iter(["pid", "name", "exe", "create_time"]):
        try:
            if (process.info["name"] or "").lower() == "madar-desk.exe":
                results[process.pid] = {
                    "exe": process.info["exe"],
                    "createTime": process.info["create_time"],
                }
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            pass
    return results


def _check_installed_untouched(before: dict) -> dict:
    import psutil
    alive = []
    for pid, identity in before.items():
        try:
            process = psutil.Process(pid)
            if (process.create_time() == identity["createTime"] and
                    process.exe() == identity["exe"] and process.is_running()):
                alive.append(pid)
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            pass
    return {"observedBefore": len(before), "sameInstancesStillRunning": len(alive),
            "allBaselineInstancesStillRunning": len(alive) == len(before)}


def _assert_no_other_qa_instance() -> None:
    import psutil
    for proc in psutil.process_iter(["name", "exe"]):
        try:
            if (proc.info["name"] or "").lower() == EXE.name.lower() and proc.is_running():
                raise RuntimeError("Other QA-bundled Madar already running: refusing overlap")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


@contextmanager
def _safe_seed_env(env: dict):
    keys = ("APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "USERPROFILE", "HOME")
    previous_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT))
    try:
        with patch.dict(os.environ, {key: env[key] for key in keys}):
            yield
    finally:
        sys.path.remove(str(ROOT))
        sys.dont_write_bytecode = previous_write_bytecode


def _seed_synthetic_gui(env: dict) -> dict:
    """Same fixture shape as the existing installed GUI test, fresh disk only."""
    with _safe_seed_env(env):
        from native_app import initial_state, atomic_save
        seed_dir = Path(env["APPDATA"]) / "MadarDesk"
        seed_dir.mkdir(parents=True, exist_ok=False)
        seed = initial_state()
        seed["workspaces"] = [{
            "id": "workspace-legacy", "name": "Synthetic bundled QA Workspace",
            "archived": False,
        }]
        seed["boards"] = [{
            "id": "qa-board", "workspaceId": "workspace-legacy",
            "projectId": "p-sample", "name": "Synthetic bundled QA Board",
            "color": "#3d977e", "archived": False, "stages": seed["stages"],
            "labelDefinitions": [], "customFields": [],
        }]
        for task in seed["tasks"]:
            if task["projectId"] == "p-sample":
                task["boardId"] = "qa-board"
                task["listId"] = task["status"]
        targets = [task for task in seed["tasks"] if task["projectId"] == "p-sample"]
        if len(targets) != 4 or len({item["title"] for item in targets}) != 4:
            raise AssertionError("Expected four unique prepopulated synthetic cards")
        atomic_save(seed_dir / "tasks.json", seed)
    return {"cardCount": len(targets), "stageCount": len(seed["stages"]),
            "target": {"id": targets[0]["id"], "projectId": targets[0]["projectId"],
                       "title": targets[0]["title"]}}


def _settings_probe(qa, pid: int) -> dict:
    """Use only own PID/HWND. Never invoke 'Open Taraz' or send on this path."""
    script = r'''
$ErrorActionPreference='Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$own=[System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]__HWND__)
if($null -eq $own){throw 'QA_WINDOW_MISSING'}
$scope=[System.Windows.Automation.TreeScope]::Descendants
$trueCond=[System.Windows.Automation.Condition]::TrueCondition
$button=[System.Windows.Automation.ControlType]::Button
$check=[System.Windows.Automation.ControlType]::CheckBox
function Nodes { return $own.FindAll($scope,$trueCond) }
function FindButton($name) {
    return @((Nodes) | Where-Object {
        $_.Current.ControlType -eq $button -and $_.Current.Name -eq $name -and
        $_.Current.IsEnabled -and -not $_.Current.IsOffscreen -and
        $_.Current.BoundingRectangle.Width -gt 5
    })
}
function InvokeOnly($name) {
    $matches=@(FindButton $name)
    if($matches.Count -ne 1){throw "BUTTON_NOT_UNIQUE: $name count=$($matches.Count)"}
    $matches[0].GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
}
InvokeOnly 'بستن'  # Close synthetic task detail, not the application.
Start-Sleep -Milliseconds 350
InvokeOnly 'تنظیمات مدار'
$settingsOpened=$false
for($i=0;$i -lt 16;$i++) {
    $tab=@(FindButton 'اتصال تراز')
    if($tab.Count -eq 1){$settingsOpened=$true;break}
    if($tab.Count -gt 1){throw 'AMBIGUOUS_TARAZ_SETTINGS_TABS'}
    Start-Sleep -Milliseconds 200
}
if(-not $settingsOpened){throw 'SETTINGS_TARAZ_TAB_NOT_RENDERED'}
InvokeOnly 'اتصال تراز'
$consent=@()
for($i=0;$i -lt 18;$i++) {
    $consent=@((Nodes) | Where-Object {
       $_.Current.ControlType -eq $check -and
       $_.Current.Name -like '*اجازهٔ ارسال دستی پیشنهاد از کارت به تراز*' -and
       -not $_.Current.IsOffscreen -and $_.Current.BoundingRectangle.Width -gt 5
    })
    if($consent.Count -eq 1){break}
    if($consent.Count -gt 1){throw 'AMBIGUOUS_CONSENT_CHECKBOX'}
    Start-Sleep -Milliseconds 200
}
if($consent.Count -ne 1){throw "TARAZ_CONSENT_NOT_RENDERED $($consent.Count)"}
$state=$consent[0].GetCurrentPattern(
    [System.Windows.Automation.TogglePattern]::Pattern).Current.ToggleState.ToString()
if($state -ne 'Off'){throw "SYNTHETIC_DEFAULT_CONSENT_NOT_OFF $state"}
$elements=@((Nodes) | Where-Object {
    $_.Current.Name -like '*تراز*' -and -not $_.Current.IsOffscreen
    } | Select-Object -First 25 | ForEach-Object { $_.Current.Name })
[pscustomobject]@{
    ownedWindowVerified=$true
    taskDrawerClosed=$true
    settingsModalOpened=$settingsOpened
    tarazSettingsTabOpened=$true
    tarazConsentCheckboxRendered=$true
    consentDefaultOff=$true
    tarazNamedControlCount=$elements.Count
    openLocalTarazClicked=$false
    manualProposalQueued=$false
} | ConvertTo-Json -Compress
'''
    return qa._run_owned_uia(pid, script, timeout=30)


def _review_disposable_proposal(root: Path, task: dict, proposal: dict) -> dict:
    """Exercise real detached Taraz local review code on the *exact* QA inbox.

    This never imports Taraz's application entrypoint, starts Taraz, changes
    a ledger, or follows a caller-supplied path.  The review is a local
    nonfinancial file transition, not proof of an authenticated peer.
    """
    if not isinstance(root, Path) or not root.is_dir() or root.is_symlink():
        raise PermissionError("Synthetic QA root must be an existing real directory")
    if (not root.name.startswith("madar-qa-bundled-taraz-") or
            root.resolve(strict=True) != root.absolute()):
        raise PermissionError("Review may only use a fresh bundled-GUI QA sandbox")
    bridge = root / "AppData" / "Local" / "Madar-Taraz-Bridge"
    for folder in (root / "AppData", root / "AppData" / "Local", bridge,
                   bridge / "pending"):
        if (not folder.is_dir() or folder.is_symlink() or
                getattr(folder, "is_junction", lambda: False)() or
                folder.resolve(strict=True) != folder.absolute()):
            raise PermissionError("Unsafe/non-disposable bridge path")
    if (not isinstance(task, dict) or not isinstance(proposal, dict) or
            not all(isinstance(task.get(key), str) and task[key]
                    for key in ("id", "projectId", "title"))):
        raise ValueError("Synthetic metadata not verified")
    request_id = proposal.get("id")
    if (type(request_id) is not str or not re.fullmatch(r"[0-9a-f]{32}", request_id)
            or set(proposal) != {
                "schema", "source", "id", "taskId", "projectId", "title", "createdUtc"
            } or proposal["schema"] != 1 or proposal["source"] != "madar"
            or proposal["taskId"] != task["id"]
            or proposal["projectId"] != task["projectId"]
            or proposal["title"] != task["title"].strip()):
        raise ValueError("Proposal is not the exact synthetic card")
    pending = bridge / "pending"
    proposal_file = pending / (request_id + ".json")
    files = list(pending.iterdir())
    if (len(files) != 1 or files[0] != proposal_file or
            proposal_file.is_symlink() or
            getattr(proposal_file, "is_junction", lambda: False)()):
        raise PermissionError("Review requires one genuine synthetic pending proposal")
    if (not proposal_file.is_file() or
            not 100 <= proposal_file.stat().st_size <= 32768):
        raise ValueError("Invalid synthetic proposal file size")
    before_bytes = proposal_file.read_bytes()
    if json.loads(before_bytes.decode("utf-8")) != proposal:
        raise ValueError("Proposal changed before review")
    safe_regular_file(DETACHED_TARAZ_REVIEW)
    taraz_source_sha = digest(DETACHED_TARAZ_REVIEW)
    taraz = _load_module(DETACHED_TARAZ_REVIEW, "mtr_nonfinancial_detached_review")
    if digest(DETACHED_TARAZ_REVIEW) != taraz_source_sha:
        raise RuntimeError("Detached Taraz source changed during import")
    decision = taraz.review_request(bridge, request_id, "reviewed")
    if digest(DETACHED_TARAZ_REVIEW) != taraz_source_sha:
        raise RuntimeError("Detached Taraz review source changed during operation")
    if (decision.get("id") != request_id or
            decision.get("state") != "reviewed" or
            decision.get("financialEventCreated") is not False):
        raise AssertionError("Synthetic detached review produced unexpected decision")
    reviewed = bridge / "reviewed"
    reviewed_file = reviewed / (request_id + ".json")
    marker = reviewed / (request_id + ".review.json")
    intent = reviewed / (request_id + ".intent.json")
    for file in (reviewed_file, marker, intent):
        safe_regular_file(file)
    if reviewed_file.read_bytes() != before_bytes or proposal_file.exists():
        raise AssertionError("Reviewed payload changed or pending proposal still exists")
    review_receipt = json.loads(marker.read_text(encoding="utf-8"))
    intent_data = json.loads(intent.read_text(encoding="utf-8"))
    if (review_receipt.get("state") != "reviewed" or
            review_receipt.get("financialEventCreated") is not False or
            intent_data.get("sourceDigest") != hashlib.sha256(before_bytes).hexdigest() or
            {key: value for key, value in intent_data.items()
             if key != "sourceDigest"} != review_receipt):
        raise AssertionError("Synthetic review markers disagree with source bytes")
    # Same reader used by the compiled native Bridge; this is NOT GUI proof.
    reader = _load_module(ROOT / "taraz_review_status.py",
                          "mtr_local_review_readback")
    local = reader.local_task_reviews(task["id"], task["projectId"],
                                      root=bridge, opted_in=True)
    if (local.get("supported") is not True or local.get("peerVerified") is not False or
            local.get("postingEnabled") is not False or
            [(item["id"], item["state"]) for item in local.get("items", [])]
            != [(request_id, "reviewed")]):
        raise AssertionError("Synthetic native review reader rejected Taraz receipt")
    return {
        "sourceModuleSha256": taraz_source_sha,
        "requestIdPrefix": request_id[:8],
        "proposalMovedWithoutMutation": True,
        "intentSourceDigestMatches": True,
        "nonfinancialReviewReceipt": True,
        "nativePythonReaderObservedReviewed": True,
        "nativePeerAuthenticated": False,
        "financialEventCreated": False,
    }


def _history_ui_readback(qa, pid: int, request_id: str) -> dict:
    """Look for reviewed state + 8-char request ID in the QA PID's real UIA tree.

    A source/compiled-asset string match is never accepted as rendered GUI.
    """
    if not isinstance(request_id, str) or not re.fullmatch(r"[0-9a-f]{32}", request_id):
        raise ValueError("QA history readback requires one exact request ID")
    prefix_b64 = base64.b64encode(request_id[:8].encode("ascii")).decode("ascii")
    script = r'''
$ErrorActionPreference='Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$own=[System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]__HWND__)
if($null -eq $own){throw 'QA_WINDOW_MISSING'}
$desc=[System.Windows.Automation.TreeScope]::Descendants
$all=[System.Windows.Automation.Condition]::TrueCondition
$btn=[System.Windows.Automation.ControlType]::Button
$id=[Text.Encoding]::ASCII.GetString([Convert]::FromBase64String('__PREFIX__'))
$expected='بررسی‌شده در تراز (غیرمالی)'
function Nodes { return $own.FindAll($desc,$all) }
function Matches($pattern) {
    return @((Nodes) | Where-Object { $_.Current.Name -like $pattern -and
        $_.Current.BoundingRectangle.Width -gt 5 -and
        -not $_.Current.IsOffscreen })
}
function Button($name) {
    return @((Nodes) | Where-Object {
        $_.Current.ControlType -eq $btn -and $_.Current.Name -eq $name -and
        $_.Current.IsEnabled -and -not $_.Current.IsOffscreen -and
        $_.Current.BoundingRectangle.Width -gt 5
    })
}
$existing=@(Matches ('*'+$expected+'*'))
if($existing.Count -ne 0){throw 'HISTORY_RESULT_ALREADY_VISIBLE_BEFORE_USER_CLICK'}
$history=@(Button 'وضعیت تراز')
if($history.Count -ne 1) {
    throw "HISTORY_BUTTON_NOT_UNIQUE_OR_ENABLED count=$($history.Count)"
}
$history[0].GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
$found=$false
$stateCount=0
$idCount=0
$jointCount=0
$sectionCount=0
$headerCount=0
$diagnostic=@()
for($i=0;$i -lt 34;$i++){
    Start-Sleep -Milliseconds 200
    $allNodes=Nodes
    $stateCount=0;$idCount=0;$jointCount=0;$sectionCount=0;$headerCount=0
    $diagnostic=@()
    foreach($item in $allNodes){
        $name=$item.Current.Name
        if([string]::IsNullOrEmpty($name)){continue}
        if($name -eq 'وضعیت تبادل محلی تراز'){$sectionCount++}
        if($name -eq 'وضعیت پیشنهادهای تراز'){$headerCount++}
        if($name.Contains($expected)){$stateCount++}
        if($name.Contains($id)){$idCount++}
        if($name.Contains($expected) -and $name.Contains($id) -and
                $item.Current.BoundingRectangle.Width -gt 5 -and
                -not $item.Current.IsOffscreen){$jointCount++}
        if($name -like '*بررسی‌شده*' -or
                $name -like ('*'+$id+'*')){
            if($diagnostic.Count -lt 6){$diagnostic+=($name.Substring(0,[Math]::Min(130,$name.Length)))}
        }
    }
    if($jointCount -ge 1 -and $headerCount -ge 1){$found=$true;break}
}
[pscustomobject]@{
    ownedQaWindowVerified=$true
    userClickedHistoryButtonOnce=$true
    historyButtonUnique=$true
    renderedHistoryHeaderCount=$headerCount
    renderedHistorySectionLabelCount=$sectionCount
    reviewedLabelNodeCount=$stateCount
    requestIdPrefixNodeCount=$idCount
    sameVisibleNodeContainsReviewedAndRequestId=$jointCount -ge 1
    reviewedHistoryRendered=$found
    uiNodeExcerpts=@($diagnostic)
    tarazExeOpened=$false
    clickedReviewAgain=$false
} | ConvertTo-Json -Compress -Depth 4
'''.replace("__PREFIX__", prefix_b64)
    return qa._run_owned_uia(pid, script, timeout=35)


def run(*, send_once_ui: bool = False, reviewed_history_ui: bool = False) -> dict:
    if not isinstance(send_once_ui, bool) or not isinstance(reviewed_history_ui, bool):
        raise TypeError("QA mode flags must be boolean")
    if send_once_ui and reviewed_history_ui:
        raise ValueError("Select exactly one synthetic send or reviewed-history QA mode")
    pinned = verify_pinned_executable()  # fail before launching anything
    qa = _load_module(REF, "mtr_installed_gui_readonly_helpers")
    before = _baseline_installed_processes()
    _assert_no_other_qa_instance()
    with tempfile.TemporaryDirectory(prefix="madar-qa-bundled-taraz-") as tmp:
        root = Path(tmp)
        env = os.environ.copy()
        for key, sub in {
            "APPDATA": "AppData/Roaming", "LOCALAPPDATA": "AppData/Local",
            "TEMP": "Temp", "TMP": "Temp", "WEBVIEW2_USER_DATA_FOLDER": "WebView2",
            "USERPROFILE": "UserProfile", "HOME": "UserProfile",
        }.items():
            directory = root / sub
            directory.mkdir(parents=True, exist_ok=True)
            env[key] = str(directory)
        # Also redirect app-specific env knobs; never inherit an opt-in launch.
        for key in list(env):
            if key.startswith("MADAR_QA_"):
                env.pop(key)
        env["MADAR_QA_REPORT"] = str(root / "gui-report.json")
        env["MADAR_QA_VIEW"] = "task-detail"
        env["MADAR_RELEASE_QA"] = "1"
        env.pop("MADAR_QA_INTERACTION", None)
        env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = "--force-renderer-accessibility"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        fixture = _seed_synthetic_gui(env)
        initial_pending = Path(env["LOCALAPPDATA"]) / "Madar-Taraz-Bridge" / "pending"
        if initial_pending.exists() or initial_pending.is_symlink():
            raise AssertionError("Synthetic bridge pending directory must start absent")
        report_path = Path(env["MADAR_QA_REPORT"])
        proc = subprocess.Popen(
            [str(EXE)], cwd=str(EXE.parent), env=env,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, close_fds=True,
        )
        try:
            end = time.monotonic() + 55
            while time.monotonic() < end:
                if report_path.is_file() and report_path.stat().st_size > 2:
                    break
                if proc.poll() is not None:
                    raise RuntimeError("QA EXE terminated before WebView2 report")
                time.sleep(0.25)
            if not report_path.is_file():
                raise RuntimeError("Current-source EXE WebView2 diagnostic did not appear")
            report = json.loads(report_path.read_text(encoding="utf-8"))
            if (not isinstance(report, dict) or report.get("rootLength", 0) < 1000
                    or report.get("bridgeType") != "object"
                    or report.get("pywebviewType") != "object"):
                raise AssertionError("Current EXE React/JS bridge not mounted")
            if (report.get("cardCount") != fixture["cardCount"] or
                    report.get("stageCount") != fixture["stageCount"]):
                raise AssertionError("Expected isolated seeded task UI not rendered")
            if proc.poll() is not None:
                raise RuntimeError("QA EXE closed before UIA access")
            initial_gui = qa._probe_own_gui(proc.pid)
            if (not initial_gui.get("qaWindowFound") or
                    not initial_gui.get("tarazButtonAccessibleAfter")):
                raise AssertionError("Current-source GUI did not render Taraz action")
            if send_once_ui or reviewed_history_ui:
                ui = qa._ui_send_once(proc.pid, fixture["target"]["title"])
                if ui.get("manualSendInvocations") != 1:
                    raise AssertionError("No uniquely targeted single GUI send")
                for _ in range(48):
                    if initial_pending.is_dir() and list(initial_pending.iterdir()):
                        break
                    time.sleep(0.25)
                # Existing installed harness's proposal readback is scoped to its
                # own prefix. Revalidate using this exact new temporary root here.
                proposals = list(initial_pending.iterdir()) if initial_pending.is_dir() else []
                if len(proposals) != 1 or proposals[0].is_symlink():
                    raise AssertionError("Expected one disposable synthetic proposal")
                proposal = json.loads(proposals[0].read_text(encoding="utf-8"))
                expected = fixture["target"]
                if (proposal.get("schema") != 1 or proposal.get("source") != "madar" or
                        proposal.get("taskId") != expected["id"] or
                        proposal.get("projectId") != expected["projectId"] or
                        proposal.get("title") != expected["title"].strip() or
                        not re.fullmatch(r"[0-9a-f]{32}", proposal.get("id", "")) or
                        proposals[0].name != proposal["id"] + ".json"):
                    raise AssertionError("Synthetic proposal failed identity/schema check")
                interaction = {"ui": ui, "pendingProposalCount": 1,
                               "syntheticIdentityMatched": True}
                if reviewed_history_ui:
                    # One exact synthetic reviewed receipt. No Taraz executable.
                    synthetic_review = _review_disposable_proposal(
                        root, fixture["target"], proposal)
                    # The task drawer remains open after the synthetic UI send.
                    # Readback MUST be proven by native Windows UI Automation.
                    gui_history = _history_ui_readback(qa, proc.pid, proposal["id"])
                    if gui_history.get("reviewedHistoryRendered") is not True:
                        raise AssertionError(
                            "Backend reviewed but GUI did not render the reviewed receipt: "
                            + json.dumps(gui_history, ensure_ascii=False))
                    interaction = {
                        "ui": ui, "syntheticReview": synthetic_review,
                        "guiHistoryReadback": gui_history,
                        "localReviewPerformedWithoutTarazExecutable": True,
                        "officialPostingVerified": False,
                    }
            else:
                interaction = _settings_probe(qa, proc.pid)
                if initial_pending.exists():
                    raise AssertionError("Observation-only GUI created proposal directory")
            return {
                "qaExe": EXE.name, "pinnedExeSha256Matched": True,
                "pinnedProof": pinned,
                "ownLaunchedPid": proc.pid,
                "freshSeparateQaWindow": True,
                "syntheticRootPrefix": root.name.split("-")[0:3],
                "reactRootMounted": True,
                "jsBridgeRuntimeObserved": report["bridgeType"],
                "pywebviewRuntimeObserved": report["pywebviewType"],
                "jsMethodNamesVerifiedStaticallyInsideArchive": list(METHODS),
                "jsMethodRuntimeTypesProbed": False,
                "renderedCards": report["cardCount"],
                "renderedStages": report["stageCount"],
                "uiAccessibility": initial_gui,
                "settingsOrManualSend": interaction,
                "installedMadarPreservation": _check_installed_untouched(before),
                "realProfileOrTarazOpened": False,
                "exeInstalledSignedOrReleased": False,
            }
        finally:
            if proc.poll() is None:
                # Close only windows with this exact new process PID or its children.
                qa._close_own_window(proc.pid)
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    import psutil
                    owner = psutil.Process(proc.pid)
                    children = owner.children(recursive=True)
                    for child in children + [owner]:
                        try:
                            child.terminate()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                    _, survivors = psutil.wait_procs(children + [owner], timeout=5)
                    if survivors:
                        raise RuntimeError("QA-owned process failed to stop; no other app touched")


if __name__ == "__main__":
    flags = sys.argv[1:]
    if flags not in ([], ["--send-isolated-ui"], ["--reviewed-history-ui"]):
        raise SystemExit("Usage: qa_mtr_current_bundled_gui_20261110.py "
                         "[--send-isolated-ui|--reviewed-history-ui]")
    print(json.dumps(run(send_once_ui=flags == ["--send-isolated-ui"],
                         reviewed_history_ui=flags == ["--reviewed-history-ui"]),
                     ensure_ascii=False, sort_keys=True))
