"""Exercise *shipped* Madar/Taraz proposal engines without touching user data.

Read-only PyInstaller extraction of modules from SHA-pinned installed EXEs;
only an isolated TemporaryDirectory is used for generated proposals/reviews.
This does not launch the installed UIs or certify financial posting/LAN.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import types
from unittest.mock import patch

from PyInstaller.archive.readers import CArchiveReader


PACKAGES = {
    "madar": (
        "MadarDesk/versions/1.0.26/Madar-Desk.exe",
        "9bb1471944fc4b31aece7470e9d433fb68e207653d865ca3881c8d5654c943a4",
        "taraz_exchange",
    ),
    "taraz": (
        "Taraz/versions/1.0.0/Taraz.exe",
        "de5005579039bd86890c1dca1f5f1d9c760e6c47579a42f649f80096f158e70c",
        "taraz_integration",
    ),
}


def _find_method_code(code: types.CodeType, method: str):
    found = []

    def walk(current):
        if current.co_name == method:
            found.append(current)
        for sub in current.co_consts:
            if isinstance(sub, types.CodeType):
                walk(sub)

    walk(code)
    if len(found) != 1:
        raise RuntimeError(f"Expected exactly one packaged {method}")
    return found[0]


def _shipped_module(local_programs: Path, name: str):
    rel_path, sha256, module_name = PACKAGES[name]
    executable = local_programs / rel_path
    if not executable.is_file() or executable.is_symlink():
        raise RuntimeError(f"{name} expected installed EXE missing or unsafe")
    if hashlib.sha256(executable.read_bytes()).hexdigest() != sha256:
        raise RuntimeError(f"{name} installed EXE version/hash mismatch")
    archive = CArchiveReader(str(executable))
    expected_api = ({"tarazIntegrationStatus", "tarazIntegrationQueue"}
                    if name == "madar" else
                    {"tarazIntegrationList", "tarazIntegrationReview"})
    javascript = [item for item in archive.toc
                  if item.startswith("dist\\assets\\") and item.endswith(".js")]
    if not javascript:
        raise RuntimeError(f"{name} shipped UI asset is missing")
    ui_code = b" ".join(archive.extract(item) for item in javascript)
    if any(method.encode("ascii") not in ui_code for method in expected_api):
        raise RuntimeError(f"{name} shipped UI lacks integration entrypoints")
    embedded = archive.open_embedded_archive("PYZ.pyz")
    code = embedded.extract(module_name)
    if not isinstance(code, types.CodeType):
        raise RuntimeError(f"{name} shipped integration module missing")
    module = types.ModuleType(f"qa_{name}_shipped")
    module.__file__ = str(executable)
    # Both selected modules have no top-level data/service I/O by design;
    # run only after APPDATA/LOCALAPPDATA etc. point to disposable fixtures.
    exec(code, module.__dict__)
    if name == "madar" and not callable(getattr(module, "queue_saved_task", None)):
        raise RuntimeError("Shipped Madar has no queue_saved_task")
    if name == "taraz" and any(not callable(getattr(module, method, None))
                              for method in ("list_requests", "review_request")):
        raise RuntimeError("Shipped Taraz has no inbox/review operations")
    entry = "native_app" if name == "madar" else "taraz_desktop"
    root_code = __import__("marshal").loads(archive.extract(entry))
    if not isinstance(root_code, types.CodeType):
        raise RuntimeError(f"{name} packaged native entry missing")
    required = ({"tarazIntegrationStatus", "tarazIntegrationQueue"}
                if name == "madar" else
                {"tarazIntegrationList", "tarazIntegrationReview"})
    methods = {method: _find_method_code(root_code, method) for method in required}
    return module, methods


def run():
    original_local = os.environ.get("LOCALAPPDATA")
    if not original_local:
        raise RuntimeError("LOCALAPPDATA is required to locate installed EXEs")
    programs = Path(original_local) / "Programs"
    if programs.is_symlink():
        raise RuntimeError("Programs path may not be a symlink")

    with tempfile.TemporaryDirectory(prefix="qa-madar-taraz-shipped-") as sandbox:
        root = Path(sandbox)
        appdata = root / "appdata"
        local = root / "local"
        appdata.mkdir()
        local.mkdir()
        with patch.dict(os.environ, {
            "APPDATA": str(appdata), "LOCALAPPDATA": str(local),
            "USERPROFILE": str(root), "HOME": str(root),
        }):
            madar, madar_native = _shipped_module(programs, "madar")
            taraz, taraz_native = _shipped_module(programs, "taraz")
            bridge = local / "Madar-Taraz-Bridge"
            state = {"tasks": [{
                "id": "synthetic-qa-task", "projectId": "synthetic-qa-project",
                "title": "SYNTHETIC QA - no accounting action",
                "checklist": [],
            }]}
            # Call the exact method bytecode shipped in each installed EXE,
            # not merely its helper module; avoid opening actual Windows UIs.
            class MadarFake:
                def __init__(self):
                    self._lock = threading.RLock()
                    self.connection = {"mode": "solo"}
                    self.remote_user = None

                def getState(self):
                    return state

            class TarazFake:
                def __init__(self):
                    self._lock = threading.RLock()
                    self.authenticated = True
                    self.can_review = True

                def _require_authenticated(self, role=None):
                    if not self.authenticated or (role == "editor" and not self.can_review):
                        raise PermissionError("synthetic unauthenticated Taraz caller")

            native_madar = MadarFake()
            native_taraz = TarazFake()
            madar_api = {method: types.FunctionType(code, {})
                         for method, code in madar_native.items()}
            taraz_api = {method: types.FunctionType(code, {"bridge_root": lambda: bridge})
                         for method, code in taraz_native.items()}
            results = []
            with patch.dict(sys.modules, {"taraz_exchange": madar,
                                          "taraz_integration": taraz}):
                status = madar_api["tarazIntegrationStatus"](native_madar)
                if not status.get("supported") or status.get("postingEnabled") is not False:
                    raise AssertionError("Packaged native Madar status not proposal-only")
                for decision in ("reviewed", "rejected"):
                    sent = madar_api["tarazIntegrationQueue"](
                        native_madar, "synthetic-qa-task", None)
                    if sent.get("postingPerformed") is not False:
                        raise AssertionError("Madar posted finance or omitted no-post guarantee")
                    request_id = sent["id"]
                    native_taraz.authenticated = False
                    try:
                        taraz_api["tarazIntegrationList"](native_taraz)
                        raise AssertionError("Unauthenticated Taraz inbox read allowed")
                    except PermissionError:
                        pass
                    native_taraz.authenticated = True
                    proposals = taraz_api["tarazIntegrationList"](native_taraz)
                    matching = [item for item in proposals["requests"]
                                if item["id"] == request_id]
                    if not proposals["connected"] or len(matching) != 1:
                        raise AssertionError("Taraz cannot read shipped Madar proposal")
                    native_taraz.can_review = False
                    try:
                        taraz_api["tarazIntegrationReview"](native_taraz, request_id, decision)
                        raise AssertionError("Taraz review allowed without editor role")
                    except PermissionError:
                        pass
                    native_taraz.can_review = True
                    receipt = taraz_api["tarazIntegrationReview"](
                        native_taraz, request_id, decision)
                    if receipt.get("financialEventCreated") is not False or receipt.get("state") != decision:
                        raise AssertionError("Shipped Taraz review did not meet non-financial contract")
                    after = taraz_api["tarazIntegrationList"](native_taraz)
                    if any(item["id"] == request_id for item in after["requests"]):
                        raise AssertionError("Reviewed request remained pending")
                    results.append(decision)
            # No user profile is accessed. No official receipt is inferred.
            return {
                "installedExecutableHashesMatched": True,
                "installedUserInterfaceAssetsContainBridgeMethods": True,
                "packagedNativeBridgeMethodsExercised": True,
                "tarazNativeAuthAndEditorRoleEnforced": True,
                "shippedBackendsConnected": len(results) == 2,
                "manualReviewAndRejection": results,
                "realProfileAccessed": False,
                "ledgerPosted": False,
                "uiOrNetworkTested": False,
            }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, sort_keys=True))
