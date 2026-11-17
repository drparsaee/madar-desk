"""End-to-end disposable Madar installed GUI -> Taraz browser review -> Madar readback.

Combines the SHA-pinned *installed Madar* GUI's real deliberate button click,
the SHA-pinned installed Taraz native inbox/review bytecode, the current
Taraz React settings UI's real deliberate browser click, and current Madar
read-only file observations against ONE private TemporaryDirectory.

No real Taraz EXE, ledger, user profile, service, installer, LAN or official
finance authority is ever used. This proves a local metadata handoff only.
"""
from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import types
from unittest.mock import patch


PROJECT = Path(__file__).resolve().parents[1]
TARAZ_ROOT = Path(r"D:\CoS-Test\000- Taraz\taraz-mtr-e2-isolated-20261109")
TARAZ_BROWSER = TARAZ_ROOT / "scripts" / "qa_taraz_review_browser_20261110.cjs"
TARAZ_NATIVE_BROWSER = TARAZ_ROOT / "scripts" / "qa_taraz_review_native_browser_20261110.cjs"


def _load_script(filename, module_name):
    target = PROJECT / "scripts" / filename
    if not target.is_file() or target.is_symlink():
        raise PermissionError("Required isolated QA source is missing or unsafe")
    spec = importlib.util.spec_from_file_location(module_name, target)
    instance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(instance)
    return instance


def _canonical_sandbox(bridge: Path):
    if not isinstance(bridge, Path) or not bridge.is_absolute():
        raise PermissionError("Expected absolute disposable QA bridge Path")
    # Inspect the original lexical path before resolving it.  Resolve-first
    # would hide a junction or symlink at the bridge itself.
    bridge = bridge.absolute()
    local = bridge.parent
    appdata = local.parent
    root = appdata.parent
    if (not root.name.startswith("madar-qa-taraz-bridge-ui-")
            or bridge != root / "AppData" / "Local" / "Madar-Taraz-Bridge"):
        raise PermissionError("Refusing external or real profile for two-app QA")
    for p in (root, appdata, local, bridge, bridge / "pending"):
        if (not p.is_dir() or p.is_symlink() or
                getattr(p, "is_junction", lambda: False)() or
                p.resolve(strict=True) != p):
            raise PermissionError("Unsafe linked QA sandbox")
    return root, local


def _read_qa_proposal(bridge, identifier, expected):
    import re
    if type(identifier) is not str or not re.fullmatch(r"[0-9a-f]{32}", identifier):
        raise PermissionError("Invalid UI-created QA proposal identifier")
    pending = bridge / "pending"
    path = pending / (identifier + ".json")
    if (not pending.is_dir() or pending.is_symlink() or
            getattr(pending, "is_junction", lambda: False)() or
            pending.resolve(strict=True) != pending or
            not path.is_file() or path.is_symlink() or
            getattr(path, "is_junction", lambda: False)() or
            path.resolve(strict=True) != path or
            path.stat().st_size > 32768):
        raise PermissionError("QA proposal not found in expected pending directory")
    if len(list(pending.iterdir())) != 1:
        raise PermissionError("QA inbox contains unexpected or duplicate proposals")

    def unique_fields(pairs):
        data = {}
        for name, value in pairs:
            if name in data:
                raise ValueError("Duplicate QA proposal field")
            data[name] = value
        return data

    record = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_fields)
    if (set(record) != {"schema", "source", "id", "taskId", "title",
                        "projectId", "createdUtc"}
            or type(record["schema"]) is not int or record["schema"] != 1
            or record["source"] != "madar" or record["id"] != identifier
            or record["taskId"] != expected["id"]
            or record["projectId"] != expected["projectId"]
            or record["title"] != expected["title"].strip()):
        raise ValueError("QA Madar UI proposal differs from saved synthetic card")
    created = record["createdUtc"]
    if not isinstance(created, str) or not 1 <= len(created) <= 50:
        raise ValueError("QA proposal timestamp is not an explicit UTC string")
    try:
        parsed = datetime.fromisoformat(created)
    except ValueError as exc:
        raise ValueError("QA proposal UTC timestamp malformed") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("QA proposal requires explicit UTC timestamp")
    return record


def _review_with_installed_taraz_and_real_browser(bridge_root, proposal_id, task,
                                                  *, decision="reviewed", native_browser=False):
    if decision not in ("reviewed", "rejected"):
        raise ValueError("Only an explicit metadata review or rejection is allowed")
    if type(native_browser) is not bool:
        raise TypeError("Native browser QA mode must be boolean")
    root, local = _canonical_sandbox(bridge_root)
    record = _read_qa_proposal(bridge_root, proposal_id, task)
    browser_runner = TARAZ_NATIVE_BROWSER if native_browser else TARAZ_BROWSER
    if not browser_runner.is_file() or browser_runner.is_symlink():
        raise PermissionError("Taraz source browser QA runner missing")

    packed = _load_script("qa_installed_madar_taraz_bridge_20261110.py",
                          "mtr_packed_taraz_qa")
    original_local = os.environ.get("LOCALAPPDATA")
    if not original_local:
        raise RuntimeError("Required installed program directory unavailable")
    installed_programs = Path(original_local) / "Programs"
    installed, native_code = packed._shipped_module(installed_programs, "taraz")

    class FakeAuthenticatedTarazInstance:
        def __init__(self):
            self._lock = threading.RLock()
            self.authenticated = True
            self.can_review = False

        def _require_authenticated(self, role=None):
            if not self.authenticated or (role == "editor" and not self.can_review):
                raise PermissionError("Synthetic Taraz host rejected role/authorization")

    taraz = FakeAuthenticatedTarazInstance()
    functions = {name: types.FunctionType(code, {"bridge_root": lambda: bridge_root})
                 for name, code in native_code.items()}
    with patch.dict(sys.modules, {"taraz_integration": installed}):
        # Actual packaged TarazAPI method invokes the role/identity gate.
        taraz.authenticated = False
        try:
            functions["tarazIntegrationList"](taraz)
            raise AssertionError("Packaged Taraz allowed anonymous inbox access")
        except PermissionError:
            pass
        taraz.authenticated = True
        inbox = functions["tarazIntegrationList"](taraz)
        if not inbox.get("connected") or inbox.get("invalidCount") != 0:
            raise AssertionError("Installed Taraz could not parse UI-created Madar proposal")
        items = [item for item in inbox.get("requests", []) if item.get("id") == proposal_id]
        if len(items) != 1 or len(inbox["requests"]) != 1:
            raise AssertionError("Installed Taraz did not find exactly one UI-created proposal")
        if any(items[0].get(key) != record[key] for key in (
                "id", "taskId", "title", "projectId", "createdUtc")):
            raise AssertionError("Packaged Taraz inbox metadata differs from GUI proposal")

        # Normal mode runs the actual React UI against an in-memory API fixture.
        # Native-browser mode uses the React UI's *actual click* to call the
        # SHA-pinned packaged Taraz bytecode through a bounded subprocess CLI.
        # Both are explicit manual-review QA, never a finance posting.
        env = os.environ.copy()
        env.update({
            "APPDATA": str(root / "AppData" / "Roaming"),
            "LOCALAPPDATA": str(local),
            "TEMP": str(root / "Temp"), "TMP": str(root / "Temp"),
        })
        if native_browser:
            original_roaming = os.environ.get("APPDATA")
            if not original_roaming:
                raise RuntimeError("Explicit read-only Playwright dependency root unavailable")
            qa_modules = Path(original_roaming) / "npm" / "node_modules"
            if not (qa_modules / "playwright").is_dir() or qa_modules.is_symlink():
                raise PermissionError("Read-only QA browser dependencies unavailable")
            env.update({
                "USERPROFILE": str(root), "HOME": str(root),
                "MTR_QA_PLAYWRIGHT_MODULES": str(qa_modules),
            })
            command = ["node", str(browser_runner), "--bridge", str(bridge_root),
                       "--programs", str(installed_programs), "--id", proposal_id]
        else:
            command = ["node", str(browser_runner)]
        if decision == "rejected":
            command.append("--reject")
        completed = subprocess.run(
            command,
            cwd=str(TARAZ_ROOT),
            input=None if native_browser else json.dumps(items[0], ensure_ascii=False),
            encoding="utf-8", errors="replace",
            capture_output=True, timeout=100 if native_browser else 45,
            env=env, check=False,
        )
        if completed.returncode:
            raise RuntimeError("Taraz actual React browser QA failed: " + completed.stderr[-900:])
        browser = json.loads(completed.stdout.strip())
        if native_browser:
            if (browser.get("status") != "PASS"
                    or browser.get("scope") != "CURRENT_TARAZ_CHROMIUM_TO_SHA_PINNED_INSTALLED_TARAZAPI_CODE"
                    or browser.get("proposalId") != proposal_id
                    or browser.get("decision") != decision
                    or browser.get("actualCurrentReactChromiumClicked") is not True
                    or browser.get("explicitManualOptIn") is not True
                    or browser.get("secondConfirmation") is not True
                    or browser.get("shippedReviewCalledByBrowser") is not True
                    or browser.get("readbackAfterReview") is not True
                    or browser.get("nativeInboxReads") != 2
                    or browser.get("nativeReviewCalls") != 1
                    or browser.get("inboxAutomaticReads") != 0
                    or browser.get("syntheticPrincipalOnly") is not True
                    or browser.get("installedTarazExeLaunched") is not False
                    or browser.get("officialTarazReceiptVerified") is not False
                    or browser.get("financialEventCreated") is not False):
                raise AssertionError("Native-browser click/backend QA contract mismatch")
        elif (browser.get("sourceTarazBrowserManualReviewClicked") is not True
              or browser.get("explicitUserClickAndConfirmation") is not True
              or browser.get("proposalId") != proposal_id
              or browser.get("decision") != decision
              or browser.get("financialEventCreated") is not False
              or browser.get("officialTarazReceiptVerified") is not False
              or browser.get("installedTarazExecutableLaunched") is not False
              or browser.get("automaticInboxReads") != 0
              or browser.get("subsequentManualAndPostReviewReads") != 2):
            raise AssertionError("Taraz browser decision did not match the same proposal")

        # The packed native TarazAPI *must* deny role revocation; the harness
        # then invokes the reviewed action exactly once after browser consent.
        try:
            functions["tarazIntegrationReview"](taraz, proposal_id, decision)
            raise AssertionError("Shipped Taraz allowed review without editor role")
        except PermissionError:
            pass
        if not native_browser:
            taraz.can_review = True
            acknowledged = functions["tarazIntegrationReview"](
                taraz, proposal_id, browser["decision"])
            if (acknowledged.get("financialEventCreated") is not False
                    or acknowledged.get("id") != proposal_id
                    or acknowledged.get("state") != decision):
                raise AssertionError("Packaged Taraz created a finance event or wrong decision")
        after = functions["tarazIntegrationList"](taraz)
        if after.get("requests") != []:
            raise AssertionError("Reviewed proposal is still in Taraz pending inbox")

    # Current Madar only observes local markers. This observation is never a
    # signed Taraz peer receipt, official invoice, or authenticated ledger write.
    if str(PROJECT) not in sys.path:
        sys.path.insert(0, str(PROJECT))
    from taraz_review_status import local_task_reviews
    status = local_task_reviews(task["id"], task["projectId"],
                                opted_in=True, root=bridge_root)
    related = [row for row in status["items"] if row.get("id") == proposal_id]
    if (len(related) != 1 or related[0]["state"] != decision
            or status["peerVerified"] is not False
            or status["postingEnabled"] is not False
            or status["scanTruncated"] is not False
            or related[0]["financialEventCreated"] is not False):
        raise AssertionError("Madar readback after native Taraz review is ambiguous")
    result = {
        "installedTarazBackendInboxAndReviewPassed": True,
        "actualCurrentTarazBrowserReviewClickPassed": True,
        "madarCurrentLocalStatusReadback": decision,
        "requestIdMatchedAcrossAllStages": True,
        "anonymousReadAndUnauthorizedReviewDenied": True,
        "installedTarazGuiWasLaunched": False,
        "officialFinancialReceiptVerified": False,
        "ledgerPostingPerformed": False,
        "realUserProfileAccessed": False,
    }
    if native_browser:
        result["actualReactClickInvokedPackagedTarazApi"] = True
        result["packagedTarazReviewCallsFromBrowser"] = browser["nativeReviewCalls"]
    return result


def run(*, decision="reviewed", native_browser=False):
    if decision not in ("reviewed", "rejected"):
        raise ValueError("Only reviewed/rejected synthetic decisions are allowed")
    if type(native_browser) is not bool:
        raise TypeError("Native browser QA mode must be boolean")
    madar_gui = _load_script("qa_installed_madar_gui_bridge_20261110.py",
                             "mtr_madar_actual_installed_gui_qa")
    def exact_disposable_callback(bridge_root, proposal_id, task):
        return _review_with_installed_taraz_and_real_browser(
            bridge_root, proposal_id, task, decision=decision,
            native_browser=native_browser)
    return madar_gui.run(send_once_ui=True,
                         on_disposable_proposal_ready=exact_disposable_callback)


if __name__ == "__main__":
    flags = sys.argv[1:]
    if len(flags) != len(set(flags)) or set(flags) - {"--reject", "--native-browser"}:
        raise SystemExit("Usage: qa_mtr_two_ui_local_cycle_20261110.py [--reject] [--native-browser]")
    print(json.dumps(run(decision="rejected" if "--reject" in flags else "reviewed",
                         native_browser="--native-browser" in flags),
                     ensure_ascii=False, sort_keys=True))
