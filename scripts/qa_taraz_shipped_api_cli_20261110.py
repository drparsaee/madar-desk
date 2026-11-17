"""QA-only CLI: invoke exact SHA-pinned installed Taraz 1.0.0 Python bytecode.

Never runs the EXE, loads any personal accounting ledger, or connects to a
network. The ONLY writable path is a strict disposable, existing Madar QA
bridge under madar-qa-taraz-bridge-ui-*/AppData/Local/Madar-Taraz-Bridge.
Auth is a plainly disclosed synthetic actor, not an actual Taraz login.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import threading
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "qa_installed_madar_taraz_bridge_20261110.py"
ID = re.compile(r"^[0-9a-f]{32}$")
ROOT_NAME = re.compile(r"^madar-qa-taraz-bridge-ui-[a-zA-Z0-9_-]{4,80}$")
MAX_BYTES = 32768
EXPECTED_HASH = "de5005579039bd86890c1dca1f5f1d9c760e6c47579a42f649f80096f158e70c"


class BoundaryError(ValueError):
    pass


def _is_link(path: Path) -> bool:
    if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
        return True
    try:
        return bool(path.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except (AttributeError, FileNotFoundError):
        return False


def _directory(path: Path):
    if (not path.is_dir() or _is_link(path)
            or path.resolve(strict=True) != path.absolute()):
        raise BoundaryError("Unsafe or missing disposable QA directory")


def validate_bridge(value: str) -> tuple[Path, Path]:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise BoundaryError("Bridge must be an explicit absolute path")
    bridge = Path(value)
    if not bridge.is_absolute():
        raise BoundaryError("Relative bridge directory prohibited")
    bridge = bridge.absolute()
    local = bridge.parent
    appdata = local.parent
    root = appdata.parent
    if (not ROOT_NAME.fullmatch(root.name)
            or bridge != root / "AppData" / "Local" / "Madar-Taraz-Bridge"):
        raise BoundaryError("Bridge is not exact ephemeral Madar QA layout")
    # The harness makes TemporaryDirectory in the process TEMP. A parent
    # launcher may itself set TEMP to <root>/Temp; support only those shapes.
    current_temp = Path(os.environ.get("TEMP") or tempfile.gettempdir()).absolute()
    if current_temp not in (root.parent, root / "Temp"):
        raise BoundaryError("QA sandbox is not owned by this temp environment")
    for part in (root, appdata, local, bridge, bridge / "pending"):
        _directory(part)
    if (root / "Temp").exists():
        _directory(root / "Temp")
    return root, bridge


def _file_bytes(path: Path, max_length: int = MAX_BYTES) -> bytes:
    if not path.is_file() or _is_link(path):
        raise BoundaryError("Missing or linked synthetic QA file")
    before = path.stat()
    if before.st_size > max_length or before.st_nlink != 1:
        raise BoundaryError("Oversized/hard-linked synthetic QA file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        if (opened.st_nlink != 1 or not stat.S_ISREG(opened.st_mode)
                or opened.st_ino != before.st_ino or opened.st_dev != before.st_dev):
            raise BoundaryError("Synthetic QA file changed while opening")
        data = os.read(fd, max_length + 1)
        after = os.fstat(fd)
        if (len(data) > max_length or after.st_size != opened.st_size
                or after.st_mtime_ns != opened.st_mtime_ns
                or _is_link(path) or path.stat().st_ino != opened.st_ino):
            raise BoundaryError("Synthetic QA file changed while reading")
        return data
    finally:
        os.close(fd)


def _unique(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise BoundaryError("Duplicate synthetic QA JSON field")
        obj[key] = value
    return obj


def _json_file(path: Path, size=MAX_BYTES):
    return json.loads(_file_bytes(path, size).decode("utf-8"),
                      object_pairs_hook=_unique)


def _metadata(record: dict, identifier: str) -> dict:
    if type(record) is not dict or set(record) != {
            "schema", "source", "id", "taskId", "projectId",
            "title", "createdUtc"}:
        raise BoundaryError("Unexpected synthetic proposal schema")
    if (type(record["schema"]) is not int or record["schema"] != 1
            or record["source"] != "madar" or record["id"] != identifier):
        raise BoundaryError("Synthetic proposal identifier/schema mismatch")
    for key, length in (("taskId", 180), ("projectId", 180), ("title", 300)):
        value = record[key]
        if type(value) is not str or not value.strip() or len(value) > length:
            raise BoundaryError("Invalid synthetic proposal metadata")
    created = record["createdUtc"]
    if type(created) is not str or len(created) > 40:
        raise BoundaryError("Invalid synthetic timestamp")
    try:
        moment = datetime.fromisoformat(created)
    except ValueError as exc:
        raise BoundaryError("Invalid synthetic timestamp") from exc
    if moment.tzinfo is None or moment.utcoffset() != timedelta(0):
        raise BoundaryError("Synthetic timestamp must be UTC")
    return record


def inspect_proposal(bridge: Path, identifier: str, *, reviewed: bool = False):
    if type(identifier) is not str or not ID.fullmatch(identifier):
        raise BoundaryError("Invalid synthetic proposal ID")
    directory = bridge / ("reviewed" if reviewed else "pending")
    _directory(directory)
    path = directory / (identifier + ".json")
    record = _json_file(path)
    return _metadata(record, identifier)


def _prereview(bridge: Path, identifier: str):
    files = list((bridge / "pending").iterdir())
    if len(files) != 1 or files[0].name != identifier + ".json":
        raise BoundaryError("QA pending inbox must contain exactly one proposal")
    if (bridge / "reviewed").exists():
        _directory(bridge / "reviewed")
        if list((bridge / "reviewed").iterdir()):
            raise BoundaryError("Unexpected historical QA review artifacts")
    return inspect_proposal(bridge, identifier)


def _review_marker(bridge: Path, identifier: str, decision: str):
    record = inspect_proposal(bridge, identifier, reviewed=True)
    reviewed = bridge / "reviewed"
    source_digest = sha256(_file_bytes(reviewed / (identifier + ".json"))).hexdigest()
    # IMPORTANT SHIPPED-1.0.0 LIMIT: unlike newer source code, the
    # SHA-pinned installed Taraz writes no durable *.intent.json or
    # sourceDigest in its review receipt. Never manufacture such proof.
    if (reviewed / (identifier + ".intent.json")).exists():
        raise BoundaryError("Unexpected source-only intent in shipped v1.0.0 review")
    receipt = _json_file(reviewed / (identifier + ".review.json"), 4096)
    required = {"schema", "id", "source", "state",
                "taskId", "reviewedUtc", "financialEventCreated"}
    if (set(receipt) != required
            or type(receipt["schema"]) is not int or receipt["schema"] != 1
            or receipt["id"] != identifier
            or receipt["source"] != "taraz"
            or receipt["state"] != decision
            or receipt["taskId"] != record["taskId"]
            or receipt["financialEventCreated"] is not False):
        raise BoundaryError("Packaged Taraz review metadata marker mismatch")
    when = receipt["reviewedUtc"]
    if type(when) is not str:
        raise BoundaryError("Shipped Taraz review has no UTC timestamp")
    try:
        moment = datetime.fromisoformat(when)
    except ValueError as exc:
        raise BoundaryError("Shipped review timestamp malformed") from exc
    if moment.tzinfo is None or moment.utcoffset() != timedelta(0):
        raise BoundaryError("Shipped review timestamp not UTC")
    return {"sourceSha256": source_digest,
            "durableSourceDigestIntentPresent": False,
            "storedReviewReceiptVerified": True}


def _read_shipped(programs: Path):
    if (not programs.is_absolute() or programs.name != "Programs"
            or _is_link(programs) or not programs.is_dir()
            or programs.resolve(strict=True) != programs.absolute()):
        raise BoundaryError("Expected absolute local installed Programs directory")
    if not HELPER.is_file() or _is_link(HELPER):
        raise BoundaryError("Read-only shipped code-object loader unavailable")
    spec = importlib.util.spec_from_file_location("qa_shipped_taraz_reader", HELPER)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    if helper.PACKAGES["taraz"][1] != EXPECTED_HASH:
        raise BoundaryError("Unexpected installed Taraz SHA pin")
    shipped, codes = helper._shipped_module(programs, "taraz")
    return shipped, codes


@contextmanager
def _sandbox_environment(root: Path, shipped):
    fields = {
        "APPDATA": str(root / "AppData" / "Roaming"),
        "LOCALAPPDATA": str(root / "AppData" / "Local"),
        "TEMP": str(root / "Temp"), "TMP": str(root / "Temp"),
        "USERPROFILE": str(root), "HOME": str(root),
        "TARAZ_QA_MODE": "1", "TARAZ_QA_DATA_DIR": str(root / "qa" / "ledger"),
        "TARAZ_DATA_DIR": str(root / "qa" / "ledger"),
    }
    with patch.dict(os.environ, fields), patch.dict(
            sys.modules, {"taraz_integration": shipped}):
        yield


class SyntheticTarazActor:
    """Explicit test double: only the actual packaged methods are tested."""
    def __init__(self, role: str, authenticated: bool):
        self._lock = threading.RLock()
        self.role = role
        self.authenticated = authenticated
        self.auth_gate_invocations = []

    def _require_authenticated(self, required=None):
        self.auth_gate_invocations.append(required)
        if not self.authenticated:
            raise PermissionError("Synthetic Taraz actor not authenticated")
        if required == "editor" and self.role != "editor":
            raise PermissionError("Synthetic Taraz role lacks editor permission")


def execute(action: str, bridge_arg: str, programs_arg: str, identifier: str,
            decision: str | None, role: str = "editor",
            authenticated: bool = True) -> dict:
    root, bridge = validate_bridge(bridge_arg)
    if type(identifier) is not str or not ID.fullmatch(identifier):
        raise BoundaryError("Invalid bound proposal identifier")
    if action not in ("preflight", "list", "review"):
        raise BoundaryError("Unknown QA action")
    if role not in ("viewer", "editor") or type(authenticated) is not bool:
        raise BoundaryError("Only explicit synthetic role/auth supported")
    if action == "review" and decision not in ("reviewed", "rejected"):
        raise BoundaryError("Unsupported metadata-only review decision")
    if action != "review" and decision is not None:
        raise BoundaryError("Unexpected review decision for read action")
    _directory(root / "AppData" / "Roaming")
    _directory(root / "Temp")
    # Preflight only confirms that this is the same reviewed, single-proposal
    # QA bridge; it never invokes the inbox API before a browser click.
    if action == "preflight":
        _prereview(bridge, identifier)
        original_sha = sha256(
            _file_bytes(bridge / "pending" / (identifier + ".json"))).hexdigest()
    elif action == "review":
        _prereview(bridge, identifier)
        original_sha = sha256(
            _file_bytes(bridge / "pending" / (identifier + ".json"))).hexdigest()
    elif action == "list" and (bridge / "pending" / (identifier + ".json")).exists():
        _prereview(bridge, identifier)

    shipped, codes = _read_shipped(Path(programs_arg))
    instance = SyntheticTarazActor(role, authenticated)
    methods = {k: types.FunctionType(v, {"bridge_root": lambda: bridge})
               for k, v in codes.items()}
    if action == "preflight":
        return {
            "schemaVersion": 1, "action": "preflight",
            "backend": "SHA_PINNED_TARAZ_1_0_0_BYTECODE",
            "installedTarazExeSha256": EXPECTED_HASH,
            "packagedMethodCodeLoaded": set(methods) == {
                "tarazIntegrationList", "tarazIntegrationReview"},
            "inboxMethodInvoked": False, "reviewMethodInvoked": False,
            "syntheticPrincipalOnly": True, "installedExeLaunched": False,
            "officialFinancePosted": False,
            "qaProposalSourceSha256": original_sha,
            "durableSourceDigestIntentPresent": False,
        }
    with _sandbox_environment(root, shipped):
        if action == "list":
            actual = methods["tarazIntegrationList"](instance)
            if type(actual) is not dict or set(actual) != {
                    "connected", "invalidCount", "requests"}:
                raise BoundaryError("Unexpected packaged Taraz inbox response")
            if (actual["connected"] is not True
                    or type(actual["invalidCount"]) is not int
                    or actual["invalidCount"] != 0
                    or type(actual["requests"]) is not list):
                raise BoundaryError("Unexpected packaged Taraz inbox status")
            rows = actual["requests"]
            if len(rows) > 1:
                raise BoundaryError("Multiple QA inbox items prohibited")
            if rows:
                original = inspect_proposal(bridge, identifier)
                read_source_sha = sha256(
                    _file_bytes(bridge / "pending" / (identifier + ".json"))).hexdigest()
                if any(rows[0].get(k) != original[k] for k in (
                        "id", "taskId", "projectId", "title", "createdUtc")):
                    raise BoundaryError("Packaged Inbox row not the QA proposal")
            else:
                # A post-review read must be backed by an already persisted
                # source-digest bound intent AND matching reviewed receipt.
                # A forged empty inbox alone cannot count as readback.
                marker_path = bridge / "reviewed" / (identifier + ".review.json")
                marker = _json_file(marker_path, 4096)
                decision = marker.get("state") if type(marker) is dict else None
                if decision not in ("reviewed", "rejected"):
                    raise BoundaryError("Empty inbox without valid QA review state")
                read_source_sha = _review_marker(bridge, identifier, decision)["sourceSha256"]
            response = {
                "connected": True, "invalidCount": 0,
                "requests": rows,
            }
            expected_gate = [None]
        else:
            actual = methods["tarazIntegrationReview"](
                instance, identifier, decision)
            if (type(actual) is not dict or set(actual) != {
                    "id", "state", "financialEventCreated"}
                    or actual != {"id": identifier, "state": decision,
                                  "financialEventCreated": False}):
                raise BoundaryError("Packaged review violated metadata-only contract")
            marker = _review_marker(bridge, identifier, decision)
            if marker["sourceSha256"] != original_sha:
                raise BoundaryError("QA proposal changed across shipped Taraz review move")
            response = actual
            read_source_sha = marker["sourceSha256"]
            expected_gate = ["editor"]
        if instance.auth_gate_invocations != expected_gate:
            raise BoundaryError("Actual packaged Taraz auth gate invocation missing")

    return {
        "schemaVersion": 1, "action": action,
        "backend": "SHA_PINNED_TARAZ_1_0_0_BYTECODE",
        "installedTarazExeSha256": EXPECTED_HASH,
        "syntheticPrincipalOnly": True, "actualPackagedTarazApiInvoked": True,
        "installedExeLaunched": False, "officialFinancePosted": False,
        "qaProposalSourceSha256": read_source_sha,
        "durableSourceDigestIntentPresent": False,
        "data": response,
    }


def _safe_reason_code(exc: Exception) -> str:
    """Fixed, privacy-safe reason labels; never echo error text or paths."""
    if isinstance(exc, UnicodeEncodeError):
        return "OUTPUT_UNICODE_ENCODING"
    if isinstance(exc, PermissionError):
        return "SYNTHETIC_AUTH_DENIED"
    if isinstance(exc, BoundaryError):
        text = str(exc)
        return {
            "QA pending inbox must contain exactly one proposal": "PENDING_CARDINALITY",
            "Unexpected synthetic proposal schema": "PROPOSAL_SCHEMA_KEYS",
            "Packaged Inbox row not the QA proposal": "PACKAGED_LIST_IDENTITY",
            "Unexpected packaged Taraz inbox response": "PACKAGED_LIST_SCHEMA",
            "Unexpected packaged Taraz inbox status": "PACKAGED_LIST_STATUS",
            "Packaged review violated metadata-only contract": "PACKAGED_REVIEW_CONTRACT",
            "Packaged Taraz review metadata marker mismatch": "PACKAGED_REVIEW_MARKER",
            "Missing or linked synthetic QA file": "QA_FILE_MISSING_OR_LINKED",
            "Synthetic proposal identifier/schema mismatch": "PROPOSAL_IDENTITY",
            "Invalid synthetic proposal metadata": "PROPOSAL_METADATA",
        }.get(text, "QA_BOUNDARY_REJECTED")
    if isinstance(exc, FileNotFoundError):
        return "QA_FILE_NOT_FOUND"
    if isinstance(exc, (UnicodeError, json.JSONDecodeError)):
        return "QA_INVALID_ENCODING_OR_JSON"
    if isinstance(exc, RuntimeError):
        return "SHIPPED_MODULE_ERROR"
    return "QA_UNCLASSIFIED_ERROR"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", choices=("preflight", "list", "review"), required=True)
    parser.add_argument("--bridge", required=True)
    parser.add_argument("--programs", required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--decision", choices=("reviewed", "rejected"))
    parser.add_argument("--role", choices=("editor", "viewer"), default="editor")
    parser.add_argument("--unauthenticated", action="store_true")
    args = parser.parse_args(argv)
    phase = "validate_input"
    try:
        phase = "run_packaged_api"
        outcome = execute(args.action, args.bridge, args.programs, args.id,
                          args.decision, args.role, not args.unauthenticated)
        # On installed Windows terminals Python stdout may be cp1252 even
        # though Node's child_process decodes UTF-8. The disposable Madar
        # GUI fixture uses a Persian title; emitting literal non-ASCII used
        # to raise UnicodeEncodeError AFTER the shipped API succeeded,
        # falsely converting its list result to QA_BLOCKED. ASCII-safe
        # JSON escapes preserve the exact Unicode title after JSON.parse.
        phase = "serialize_response"
        print(json.dumps(outcome, ensure_ascii=True, sort_keys=True))
        return 0
    except (BoundaryError, PermissionError, FileNotFoundError, RuntimeError,
            AssertionError, ValueError, OSError, UnicodeError) as exc:
        # Deliberately no traceback, ledger content, user profile or path in
        # the JSON contract. A failed operation cannot become a UI success.
        code = "AUTH_DENIED" if isinstance(exc, PermissionError) else "QA_BLOCKED"
        print(json.dumps({
            "schemaVersion": 1, "action": args.action,
            "status": "DENIED", "errorCode": code,
            "phase": phase,
            "reasonCode": _safe_reason_code(exc),
            "installedExeLaunched": False, "officialFinancePosted": False,
        }, sort_keys=True))
        print(f"Taraz synthetic packaged-API QA denied: {type(exc).__name__}",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
