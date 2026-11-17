"""Same-user local Taraz installation probe and explicit manual opener.

Not a financial receipt, network connection, or peer authentication. The
desktop can launch only a SHA-pinned installed executable on a deliberate click.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess


_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z", re.ASCII)
# Only previously inspected installed releases can be launched from Madar.
_APPROVED = {
    "1.0.0": "de5005579039bd86890c1dca1f5f1d9c760e6c47579a42f649f80096f158e70c",
}


class TarazPeerUnavailable(PermissionError):
    """Unknown, absent, changed or unreviewed Taraz executable."""


def _regular(path):
    if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
        raise TarazPeerUnavailable("unsafe Taraz path")
    item = path.lstat()
    if (not stat.S_ISREG(item.st_mode) or item.st_nlink != 1 or
            getattr(item, "st_file_attributes", 0) & 0x400):
        raise TarazPeerUnavailable("unsafe Taraz file")
    return item


def _directory(path):
    if (path.is_symlink() or getattr(path, "is_junction", lambda: False)()
            or not path.is_dir() or
            getattr(path.lstat(), "st_file_attributes", 0) & 0x400):
        raise TarazPeerUnavailable("unsafe Taraz installation folder")


def _approved_executable(*, localappdata=None, approved=None):
    local = localappdata if localappdata is not None else os.environ.get("LOCALAPPDATA")
    if type(local) is not str or not local or not Path(local).is_absolute():
        raise TarazPeerUnavailable("Windows user installation root unavailable")
    root = Path(local) / "Programs" / "Taraz"
    for folder in (Path(local), Path(local) / "Programs", root, root / "versions"):
        _directory(folder)
    pointer = root / "current-version.txt"
    pointer_info = _regular(pointer)
    if not 1 <= pointer_info.st_size <= 32:
        raise TarazPeerUnavailable("invalid Taraz version pointer")
    version = pointer.read_text(encoding="utf-8-sig").strip()
    known = _APPROVED if approved is None else approved
    if not _VERSION.fullmatch(version) or version not in known:
        raise TarazPeerUnavailable("Taraz version not approved for local pairing")
    directory = root / "versions" / version
    _directory(directory)
    exe = directory / "Taraz.exe"
    before = _regular(exe)
    if not 1_000_000 <= before.st_size <= 200_000_000:
        raise TarazPeerUnavailable("invalid Taraz binary size")
    digest = hashlib.sha256()
    with exe.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != known[version]:
        raise TarazPeerUnavailable("installed Taraz binary digest mismatch")
    after = _regular(exe)
    if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) !=
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
        raise TarazPeerUnavailable("Taraz changed during inspection")
    return version, exe


def local_peer_status():
    """No claim that Taraz is running, logged in or an accounting authority."""
    try:
        version, _ = _approved_executable()
    except (TarazPeerUnavailable, OSError, ValueError, UnicodeError):
        return {"installed": False, "approvedBuild": False, "version": None,
                "canOpenManually": False, "peerAuthenticated": False,
                "financialPostingEnabled": False}
    return {"installed": True, "approvedBuild": True, "version": version,
            "canOpenManually": True, "peerAuthenticated": False,
            "financialPostingEnabled": False}


def open_local_taraz(*, manual_action):
    """Explicit UI action only; Taraz itself handles login and normal startup."""
    if manual_action is not True:
        raise PermissionError("explicit human launch action required")
    version, executable = _approved_executable()
    subprocess.Popen([str(executable)], cwd=str(executable.parent),
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True)
    return {"launchRequested": True, "version": version,
            "peerAuthenticated": False, "financialEventCreated": False}


__all__ = ["local_peer_status", "open_local_taraz", "TarazPeerUnavailable"]
