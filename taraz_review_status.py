"""Bounded, read-only local proposal lifecycle inspection (not financial approval).

The caller must authorize the selected persisted task and obtain explicit UI consent.
The filesystem is not an authenticated peer: these are *local file observations*.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat

_ID = re.compile(r"[0-9a-f]{32}\Z")
_MAX_BYTES = 32768
_MAX_FILES = 200


def _unsafe(path: Path) -> bool:
    if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
        return True
    if path.exists():
        return bool(getattr(path.lstat(), "st_file_attributes", 0) &
                    getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    return False


def _load(path: Path, *, digest: bool = False):
    if _unsafe(path) or not path.is_file():
        raise ValueError("Unsafe proposal path")
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > _MAX_BYTES:
        raise ValueError("Oversized proposal")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1 or
                (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)):
            raise ValueError("Proposal replaced during opening")
        with os.fdopen(fd, "rb", closefd=False) as source:
            raw = source.read(_MAX_BYTES + 1)
        after = os.fstat(fd)
        current = path.lstat()
        if (_unsafe(path) or (current.st_dev, current.st_ino) !=
                (opened.st_dev, opened.st_ino) or
                (after.st_size, after.st_mtime_ns) !=
                (opened.st_size, opened.st_mtime_ns)):
            raise ValueError("Proposal changed while reading")
    finally:
        os.close(fd)
    if len(raw) > _MAX_BYTES:
        raise ValueError("Oversized proposal")
    def unique(items):
        result = {}
        for key, item in items:
            if key in result:
                raise ValueError("Duplicate proposal key")
            result[key] = item
        return result
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ValueError("Invalid proposal object")
    return (value, hashlib.sha256(raw).hexdigest()) if digest else value


def _proposal(value: dict, identifier: str, task_id: str, project_id: str) -> bool:
    return (value.get("schema") == 1 and value.get("source") == "madar" and
            value.get("id") == identifier and value.get("taskId") == task_id and
            value.get("projectId") == project_id and
            isinstance(value.get("title"), str) and bool(value["title"].strip()) and
            isinstance(value.get("createdUtc"), str) and
            1 <= len(value["createdUtc"]) <= 50 and "T" in value["createdUtc"])


def local_task_reviews(task_id: str, project_id: str, *, opted_in: bool = False,
                       root: Path | None = None) -> dict:
    """Return scoped local observations; never infer formal accounting status.

    root is a trusted native path, not a frontend-supplied input. Results are
    constrained to the selected task and project. Missing/partial data is unknown.
    """
    if type(opted_in) is not bool:
        raise TypeError("opted_in must be boolean")
    if not opted_in:
        return {"supported": True, "state": "disabled", "items": [],
                "peerVerified": False, "postingEnabled": False}
    if not isinstance(task_id, str) or not 1 <= len(task_id) <= 180 or not task_id.strip():
        raise ValueError("Invalid task identifier")
    if not isinstance(project_id, str) or not 1 <= len(project_id) <= 180 or not project_id.strip():
        raise ValueError("Invalid project identifier")
    if root is None:
        local = os.environ.get("LOCALAPPDATA")
        if not local:
            return {"supported": False, "state": "unavailable", "items": [],
                    "peerVerified": False, "postingEnabled": False}
        root = Path(local) / "Madar-Taraz-Bridge"
    result = {"supported": True, "state": "observed", "items": [],
              "peerVerified": False, "postingEnabled": False, "scanTruncated": False}
    try:
        if _unsafe(root):
            raise ValueError("Unsafe exchange root")
        directories = [root / "pending", root / "reviewed"]
        if any(_unsafe(folder) for folder in directories):
            raise ValueError("Unsafe exchange folder")
        records = {}
        for folder in directories:
            if not folder.is_dir():
                continue
            with os.scandir(folder) as iterator:
                for index, entry in enumerate(iterator):
                    if index >= _MAX_FILES:
                        result["scanTruncated"] = True
                        break
                    if not entry.name.endswith(".json") or entry.name.endswith(".review.json"):
                        continue
                    identifier = entry.name[:-5]
                    if not _ID.fullmatch(identifier) or not entry.is_file(follow_symlinks=False):
                        continue
                    path = folder / entry.name
                    try:
                        data = _load(path)
                    except (ValueError, OSError, UnicodeError, TypeError):
                        continue
                    if _proposal(data, identifier, task_id, project_id):
                        records.setdefault(identifier, {})[folder.name] = data
        for identifier, locations in records.items():
            pending = "pending" in locations
            processed = "reviewed" in locations
            state = "pending" if pending and not processed else "unknown"
            reviewed_utc = None
            if processed and not pending:
                marker = directories[1] / (identifier + ".review.json")
                try:
                    receipt = _load(marker)
                    if (set(receipt) == {"schema", "id", "source", "state",
                                         "reviewedUtc", "taskId", "financialEventCreated"} and
                        receipt.get("schema") == 1 and receipt.get("source") == "taraz" and
                        receipt.get("id") == identifier and receipt.get("taskId") == task_id and
                        receipt.get("financialEventCreated") is False and
                        receipt.get("state") in ("reviewed", "rejected") and
                        isinstance(receipt.get("reviewedUtc"), str) and
                        1 <= len(receipt["reviewedUtc"]) <= 50):
                        # Legacy installed Taraz did not persist a durable
                        # source-bound intent. A receipt without this evidence
                        # is UNKNOWN, never a confirmed local review. Even a
                        # consistent intent is not authenticated peer proof.
                        intent_file = directories[1] / (identifier + ".intent.json")
                        intent_consistent = False
                        if intent_file.exists() or _unsafe(intent_file):
                            intent = _load(intent_file)
                            _, source_digest = _load(
                                directories[1] / (identifier + ".json"), digest=True)
                            intent_consistent = (
                                set(intent) == set(receipt) | {"sourceDigest"} and
                                {k: v for k, v in intent.items() if k != "sourceDigest"} == receipt and
                                intent.get("sourceDigest") == source_digest)
                        if intent_consistent:
                            state = receipt["state"]
                            reviewed_utc = receipt["reviewedUtc"]
                except (ValueError, OSError, UnicodeError, TypeError):
                    pass
            result["items"].append({"id": identifier, "state": state,
                                    "createdUtc": locations.get("pending", locations.get("reviewed"))["createdUtc"],
                                    "reviewedUtc": reviewed_utc, "financialEventCreated": False})
        result["items"].sort(key=lambda item: str(item["createdUtc"]), reverse=True)
        result["items"] = result["items"][:100]
        if result["scanTruncated"]:
            result["state"] = "partial"
    except (OSError, ValueError):
        result.update({"supported": False, "state": "unavailable", "items": []})
    return result
