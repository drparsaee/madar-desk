"""New NONRELEASE Madar QA EXE: real GUI durable-vs-legacy local Taraz history.

Read-only imports existing synthetic QA helpers, never their installed-app run.
Only one SHA-pinned, uninstalled QA EXE is launched. All app/webview data live
in a fresh private TemporaryDirectory; no real profile, ledger, LAN or Taraz
executable is opened. Positive/negative outcomes require actual PID-owned UIA.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
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

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = Path(
    r"D:\CoS-Test\MTR-MADAR-TARAZ-QA-BUNDLE-20261110"
    r"\run-20261110-183506-18748-ec491e30"
)
EXE = BUNDLE / "exe-dist" / "Madar-Taraz-Connection-QA-20261110-NONRELEASE.exe"
SHA_EXE = "0ba37c211f738d3d7bb9cf2a794a904f0269de128f72dfa8f1662755ac719454"
SHA_PROOF = "0689d26c3a554bef7995abf51b038c49af050adb44a86563a3227a6da92ee297"
SHA_ASSETS = "4761efc7980e523a3089b1889e4b135d1854fabfd19c45a4fb768597a0472021"
SHA_NATIVE = "1f24e4b45513382f00a872f09a9d1d04bd183a19718f18cf62ad7596f087808b"
SHA_UI = "a057d2d336a8c9393d7b2c199f7a1a156a01f0f4ae8b2e1a01c82bc7be437e8f"
SHA_TREE = "1f4853ff34db15dbe49281003f15cbe0ec1ea39689ac7dafe267409bc3409617"
_METHODS = frozenset({
    "tarazIntegrationOpenLocal", "tarazIntegrationPrepare",
    "tarazIntegrationQueue", "tarazIntegrationHistory",
})
OLD = ROOT / "scripts" / "qa_mtr_current_bundled_gui_20261110.py"
GUI = ROOT / "scripts" / "qa_installed_madar_gui_bridge_20261110.py"
BUILDER = ROOT / "scripts" / "qa_mtr_connection_build_20261110.py"
_ID = re.compile(r"[0-9a-f]{32}\Z", re.ASCII)


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fd:
        for part in iter(lambda: fd.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def _regular(path: Path):
    if (not path.is_file() or path.is_symlink() or
            getattr(path, "is_junction", lambda: False)()):
        raise PermissionError("Unsafe/missing pinned QA file")
    meta = path.lstat()
    if (meta.st_nlink != 1 or
            getattr(meta, "st_file_attributes", 0) & 0x400):
        raise PermissionError("Unsafe linked/reparse QA file")


def _module(path: Path, name: str):
    _regular(path)
    spec = importlib.util.spec_from_file_location(name, str(path))
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def verify_bundle() -> dict:
    """Fail before launching if EXACT nonrelease EXE/provenance/asset pins drift."""
    if os.name != "nt":
        raise RuntimeError("Windows required")
    artifacts = (
        (EXE, SHA_EXE), (BUNDLE / "qa-provenance.json", SHA_PROOF),
        (BUNDLE / "vite-assets-sha256.json", SHA_ASSETS),
        (BUNDLE / "source" / "native_app.py", SHA_NATIVE),
        (BUNDLE / "source" / "src" / "App.jsx", SHA_UI),
        (ROOT / "native_app.py", SHA_NATIVE),
        (ROOT / "src" / "App.jsx", SHA_UI),
    )
    for path, expected in artifacts:
        _regular(path)
        if _hash(path) != expected:
            raise PermissionError("Pinned QA artifact/source digest mismatch: " + path.name)
    proof = json.loads((BUNDLE / "qa-provenance.json").read_text(encoding="utf8"))
    assets = json.loads((BUNDLE / "vite-assets-sha256.json").read_text(encoding="utf8"))
    _regular(BUNDLE / "qa-build-result.json")
    build = json.loads((BUNDLE / "qa-build-result.json").read_text(encoding="utf8"))
    if (proof.get("schemaVersion") != 1 or
            proof.get("purpose") != "NON_RELEASE_QA" or
            proof.get("notFunctionalTestOrReleaseApproval") is not True or
            proof.get("sourceFileCount") != 6502 or
            proof.get("sourceSnapshotTreeSha256") != SHA_TREE or
            proof.get("nativeSourceSha256") != SHA_NATIVE or
            proof.get("uiSourceSha256") != SHA_UI or
            proof.get("viteAssetsSha256") != SHA_ASSETS or
            not isinstance(assets, dict) or len(assets) != 16 or
            build.get("application", {}).get("sha256") != SHA_EXE or
            build.get("application", {}).get("releaseReady") is not False or
            set(build.get("application", {}).get("compiledBridgeMethods", [])) != _METHODS):
        raise PermissionError("Bundle manifest is not the pinned QA-only build")
    builder = _module(BUILDER, "mtr_new_qa_builder_read_only")
    archive = builder.verify_exe(EXE, BUNDLE / "qa-provenance.json", assets)
    if (archive.get("embeddedProvenanceMatches") is not True or
            archive.get("embeddedViteAssetsVerified") != 16 or
            set(archive.get("compiledBridgeMethods", [])) != _METHODS or
            archive.get("releaseReady") is not False or
            archive.get("sha256") != SHA_EXE):
        raise PermissionError("Compiled QA archive or Vite proof mismatch")
    return {
        "sha256Matched": True, "nonRelease": True,
        "manifestSourceFileCount": 6502, "manifestTreeSha256Matched": True,
        "compiledBridgeMethodsMatched": True,
        "embeddedViteAssetsVerified": 16,
    }


@contextmanager
def _disposable_root():
    owned = tempfile.TemporaryDirectory(prefix="madar-qa-bundled-taraz-")
    try:
        yield Path(owned.name)
    finally:
        path = Path(owned.name)
        if (not path.is_absolute() or
                not path.name.startswith("madar-qa-bundled-taraz-") or
                path.is_symlink() or getattr(path, "is_junction", lambda: False)()):
            raise PermissionError("Refusing cleanup outside exact QA sandbox")
        for attempt in range(20):
            try:
                owned.cleanup()
                break
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(.25)


def _history_ui_readback(gui, pid: int, request_id: str) -> dict:
    """Actual GUI can show only an unauthenticated LOCAL marker, never verified Taraz."""
    if type(request_id) is not str or not _ID.fullmatch(request_id):
        raise ValueError("Exact QA request ID required")
    prefix = base64.b64encode(request_id[:8].encode("ascii")).decode("ascii")
    script = r'''
$ErrorActionPreference='Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$own=[System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]__HWND__)
if($null -eq $own){throw 'QA_WINDOW_MISSING'}
$desc=[System.Windows.Automation.TreeScope]::Descendants
$condition=[System.Windows.Automation.Condition]::TrueCondition
$btn=[System.Windows.Automation.ControlType]::Button
$id=[Text.Encoding]::ASCII.GetString([Convert]::FromBase64String('__PREFIX__'))
$expected='علامت بررسی‌شده در فایل محلی (هویت تراز تأییدنشده)'
$forbidden='بررسی‌شده توسط همتای احرازشده (غیرمالی)'
function Nodes {return $own.FindAll($desc,$condition)}
function HistoryButton {
  return @((Nodes)|Where-Object {$_.Current.ControlType -eq $btn -and
    $_.Current.Name -eq 'وضعیت تراز' -and $_.Current.IsEnabled -and
    -not $_.Current.IsOffscreen -and $_.Current.BoundingRectangle.Width -gt 5})
}
$prior=@((Nodes)|Where-Object {$_.Current.Name.Contains($expected)})
if($prior.Count -gt 0){throw 'QA_HISTORY_VISIBLE_BEFORE_MANUAL_CLICK'}
$button=@(HistoryButton)
if($button.Count -ne 1){throw "QA_HISTORY_BUTTON_COUNT $($button.Count)"}
$button[0].GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
$seen=0;$wrong=0;$header=0
for($i=0;$i -lt 35;$i++){
  Start-Sleep -Milliseconds 200
  $seen=0;$wrong=0;$header=0
  foreach($element in (Nodes)){
    $name=$element.Current.Name
    if([string]::IsNullOrEmpty($name) -or $element.Current.IsOffscreen -or
        $element.Current.BoundingRectangle.Width -le 5){continue}
    if($name -eq 'وضعیت پیشنهادهای تراز'){$header++}
    if($name.Contains($expected) -and $name.Contains($id)){$seen++}
    if($name.Contains($forbidden) -and $name.Contains($id)){$wrong++}
  }
  if($seen -gt 0 -and $header -gt 0){break}
}
[pscustomobject]@{
  ownedQaWindowVerified=$true
  userClickedHistoryButtonOnce=$true
  reviewedHistoryRendered=($seen -gt 0 -and $header -gt 0 -and $wrong -eq 0)
  sameVisibleNodeContainsReviewedAndRequestId=($seen -gt 0)
  unverifiedLocalHistoryClearlyLabeled=($seen -gt 0)
  forgedPeerVerifiedHistoryRendered=($wrong -gt 0)
  reviewedNodeCount=$seen
  verifiedLabelNodeCount=$wrong
  localHistoryHeaderCount=$header
  officialPostingVerified=$false
} | ConvertTo-Json -Compress
'''.replace('__PREFIX__', prefix)
    return gui._run_owned_uia(pid, script, timeout=35)


def _legacy_ui_readback(gui, pid: int, request_id: str) -> dict:
    """Invoke History again AFTER synthetic intent removal; require UNKNOWN."""
    if type(request_id) is not str or not _ID.fullmatch(request_id):
        raise ValueError("Exact QA request ID required")
    prefix = base64.b64encode(request_id[:8].encode("ascii")).decode("ascii")
    script = r'''
$ErrorActionPreference='Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$own=[System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]__HWND__)
if($null -eq $own){throw 'QA_WINDOW_MISSING'}
$tree=[System.Windows.Automation.TreeScope]::Descendants
$condition=[System.Windows.Automation.Condition]::TrueCondition
$button=[System.Windows.Automation.ControlType]::Button
$prefix=[Text.Encoding]::ASCII.GetString([Convert]::FromBase64String('__PREFIX__'))
$positive='علامت بررسی‌شده در فایل محلی (هویت تراز تأییدنشده)'
$negative='وضعیت نامعلوم'
function Nodes {return $own.FindAll($tree,$condition)}
function TargetButton {
  return @((Nodes)|Where-Object {
    $_.Current.ControlType -eq $button -and
    $_.Current.Name -eq 'وضعیت تراز' -and
    $_.Current.IsEnabled -and -not $_.Current.IsOffscreen -and
    $_.Current.BoundingRectangle.Width -gt 5
  })
}
$before=@((Nodes)|Where-Object {
  $_.Current.Name.Contains($positive) -and
  $_.Current.Name.Contains($prefix) -and
  $_.Current.BoundingRectangle.Width -gt 5 -and -not $_.Current.IsOffscreen
})
if($before.Count -lt 1){throw 'POSITIVE_HISTORY_NOT_VISIBLE_BEFORE_LEGACY_REFRESH'}
$target=@(TargetButton)
if($target.Count -ne 1){throw "HISTORY_REFRESH_BUTTON_AMBIGUOUS $($target.Count)"}
$target[0].GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
$unknown=0;$reviewed=0;$header=0
$complete=$false
for($attempt=0;$attempt -lt 35;$attempt++){
  Start-Sleep -Milliseconds 200
  $unknown=0;$reviewed=0;$header=0
  foreach($node in (Nodes)){
    $name=$node.Current.Name
    if([string]::IsNullOrEmpty($name) -or
       $node.Current.IsOffscreen -or
       $node.Current.BoundingRectangle.Width -le 5){continue}
    if($name -eq 'وضعیت پیشنهادهای تراز'){$header++}
    if($name.Contains($prefix) -and $name.Contains($negative)){$unknown++}
    if($name.Contains($prefix) -and $name.Contains($positive)){$reviewed++}
  }
  if($header -gt 0 -and $unknown -gt 0 -and $reviewed -eq 0){$complete=$true;break}
}
[pscustomobject]@{
  ownQaWindowVerified=$true
  historyRefreshedByUiClick=$true
  legacyMarkerShownAsReviewed=$reviewed -gt 0
  legacyMarkerRefused=$complete
  unknownSameIdNodeCount=$unknown
  reviewedSameIdNodeCount=$reviewed
  financialDocumentVerified=$false
} | ConvertTo-Json -Compress
'''.replace("__PREFIX__", prefix)
    return gui._run_owned_uia(pid, script, timeout=35)


def _read_proposal(pending: Path, expected: dict):
    if (not pending.is_dir() or pending.is_symlink() or
            getattr(pending, "is_junction", lambda: False)()):
        raise PermissionError("Disposable pending dir missing or linked")
    files = list(pending.iterdir())
    if len(files) != 1:
        raise AssertionError("GUI must create exactly one synthetic proposal")
    file = files[0]
    _regular(file)
    if not 100 <= file.stat().st_size <= 32768:
        raise AssertionError("GUI proposal size invalid")
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise AssertionError("Duplicate proposal JSON property")
            obj[key] = value
        return obj
    record = json.loads(file.read_text(encoding="utf8"), object_pairs_hook=unique)
    if (type(record) is not dict or
            set(record) != {"schema", "source", "id", "taskId",
                            "projectId", "title", "createdUtc"} or
            type(record["schema"]) is not int or record["schema"] != 1 or
            record["source"] != "madar" or
            type(record["id"]) is not str or not _ID.fullmatch(record["id"]) or
            file.name != record["id"] + ".json" or
            record["taskId"] != expected["id"] or
            record["projectId"] != expected["projectId"] or
            record["title"] != expected["title"].strip()):
        raise AssertionError("GUI synthetic proposal scope/schema mismatch")
    return record


def _close_only_qa(proc, gui) -> None:
    """Close only the EXE launched by THIS Popen and verified descendants."""
    import psutil
    own = None
    descendants = []
    if proc.poll() is None:
        try:
            own = psutil.Process(proc.pid)
            if own.is_running():
                descendants = own.children(recursive=True)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        gui._close_own_window(proc.pid)
        try:
            proc.wait(timeout=7)
        except subprocess.TimeoutExpired:
            proc.kill()  # only Popen's retained handle
            proc.wait(timeout=5)
    if descendants:
        _, alive = psutil.wait_procs(descendants, timeout=2)
        for child in alive:
            try:
                child.terminate()  # psutil handle with retained create_time
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs(alive, timeout=4)
        if alive:
            raise RuntimeError("QA-owned browser workers survived bounded cleanup")
    if proc.poll() is None:
        raise RuntimeError("QA EXE did not exit")


def run() -> dict:
    pinned = verify_bundle()
    old = _module(OLD, "mtr_new_bundle_seed_and_review_read_only")
    gui = _module(GUI, "mtr_new_bundle_uia_read_only")
    before = old._baseline_installed_processes()
    # Identical basename may be running in another QA; never manipulate it.
    original = old.EXE
    try:
        old.EXE = EXE
        old._assert_no_other_qa_instance()
    finally:
        old.EXE = original
    with _disposable_root() as root:
        env = os.environ.copy()
        for name, rel in {
            "APPDATA": "AppData/Roaming", "LOCALAPPDATA": "AppData/Local",
            "TEMP": "Temp", "TMP": "Temp",
            "WEBVIEW2_USER_DATA_FOLDER": "WebView2",
            "USERPROFILE": "UserProfile", "HOME": "UserProfile",
        }.items():
            target = root / rel
            target.mkdir(parents=True, exist_ok=True)
            env[name] = str(target)
        for key in list(env):
            if key.startswith("MADAR_QA_"):
                env.pop(key)
        env.update({
            "MADAR_QA_REPORT": str(root / "gui-report.json"),
            "MADAR_QA_VIEW": "task-detail", "MADAR_RELEASE_QA": "1",
            "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS": "--force-renderer-accessibility",
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        fixture = old._seed_synthetic_gui(env)
        pending = Path(env["LOCALAPPDATA"]) / "Madar-Taraz-Bridge" / "pending"
        if pending.exists() or pending.is_symlink():
            raise AssertionError("Non-empty disposable QA inbox before launch")
        report_path = Path(env["MADAR_QA_REPORT"])
        proc = subprocess.Popen(
            [str(EXE)], cwd=str(EXE.parent), env=env,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, close_fds=True,
        )
        try:
            deadline = time.monotonic() + 55
            while time.monotonic() < deadline:
                if report_path.is_file() and report_path.stat().st_size > 2:
                    break
                if proc.poll() is not None:
                    raise RuntimeError("QA EXE exited before JS/React diagnostic")
                time.sleep(.25)
            if not report_path.is_file():
                raise RuntimeError("QA EXE did not provide its WebView2 report")
            report = json.loads(report_path.read_text(encoding="utf8"))
            if (type(report) is not dict or report.get("rootLength", 0) < 1000 or
                    report.get("bridgeType") != "object" or
                    report.get("pywebviewType") != "object" or
                    report.get("cardCount") != fixture["cardCount"] or
                    report.get("stageCount") != fixture["stageCount"]):
                raise AssertionError("Compiled QA app/bridge/synthetic cards not mounted")
            observed = gui._probe_own_gui(proc.pid)
            if observed.get("tarazButtonAccessibleAfter") is not True:
                raise AssertionError("New QA GUI Taraz send action not visible")
            ui_send = gui._ui_send_once(proc.pid, fixture["target"]["title"])
            if ui_send.get("manualSendInvocations") != 1:
                raise AssertionError("New QA GUI must send exactly once")
            for _ in range(48):
                if pending.is_dir() and list(pending.iterdir()):
                    break
                time.sleep(.25)
            record = _read_proposal(pending, fixture["target"])
            # Current Taraz source performs a real *local metadata review*.
            review = old._review_disposable_proposal(root, fixture["target"], record)
            if (review.get("nativePythonReaderObservedReviewed") is not True or
                    review.get("intentSourceDigestMatches") is not True or
                    review.get("financialEventCreated") is not False):
                raise AssertionError("Current Taraz metadata review not durable")
            durable_ui = _history_ui_readback(gui, proc.pid, record["id"])
            if (durable_ui.get("reviewedHistoryRendered") is not True or
                    durable_ui.get("sameVisibleNodeContainsReviewedAndRequestId") is not True or
                    durable_ui.get("unverifiedLocalHistoryClearlyLabeled") is not True or
                    durable_ui.get("forgedPeerVerifiedHistoryRendered") is not False):
                raise AssertionError("New QA GUI failed to display durable review history")
            reviewed = Path(env["LOCALAPPDATA"]) / "Madar-Taraz-Bridge" / "reviewed"
            intent = reviewed / (record["id"] + ".intent.json")
            _regular(intent)
            intent.unlink()  # precise disposable synthetic-only legacy downgrade
            local_reader = _module(ROOT / "taraz_review_status.py",
                                   "mtr_new_qa_legacy_reader_read_only")
            observed_legacy = local_reader.local_task_reviews(
                fixture["target"]["id"], fixture["target"]["projectId"],
                opted_in=True, root=reviewed.parent)
            rows = [item for item in observed_legacy.get("items", [])
                    if item.get("id") == record["id"]]
            if (len(rows) != 1 or rows[0].get("state") != "unknown" or
                    observed_legacy.get("peerVerified") is not False):
                raise AssertionError("Current reader accepted intent-less legacy marker")
            legacy_ui = _legacy_ui_readback(gui, proc.pid, record["id"])
            if (legacy_ui.get("legacyMarkerRefused") is not True or
                    legacy_ui.get("legacyMarkerShownAsReviewed") is not False):
                raise AssertionError("New QA GUI trusted legacy marker without intent")
            return {
                "newQaExecutableSha256Matched": True,
                "qaOnlyManifestPinned": pinned,
                "currentBundleReactMounted": True,
                "ownQaGuiTarazClickedOnce": True,
                "durableSourceReviewViaCurrentTaraz": review,
                "durableReviewedHistoryRenderedInRealGui": True,
                "legacyMarkerWithoutIntentRefusedInRealGui": True,
                "durableHistoryUi": durable_ui,
                "legacyHistoryUi": legacy_ui,
                "baselineUserMadarPreserved": old._check_installed_untouched(before),
                "peerVerified": False, "officialPostingVerified": False,
                "realProfilesOrInstalledExeOpened": False, "releaseApproved": False,
            }
        finally:
            _close_only_qa(proc, gui)


if __name__ == "__main__":
    if sys.argv[1:]:
        raise SystemExit("Usage: qa_mtr_new_bundle_gui_20261110.py")
    print(json.dumps(run(), ensure_ascii=False, sort_keys=True))
