"""Standalone E7 read-only, fail-closed release build eligibility preflight.

NO building, installation, signing, service launch, profile inspection or
network. A file's existence is never proof of a Microsoft signature, full
offline WebView2 runtime, build freshness, or accepted financial workflows.

Usage: py -3.12 -B tools/mtr_release_readiness.py [--root ABSOLUTE_FIXTURE_ROOT]
The optional root requires a disposable synthetic fixture ownership marker.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys


EXPECTED_VERSION = "1.0.23"
SYNTHETIC_MARKER = ".mtr-release-readiness-fixture.json"
SYNTHETIC_OWNERSHIP = {"owner": "mtr-release-readiness", "synthetic": True}
PREREQUISITE = "release/.madar-inno-prereq/MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
REQUIRED_SOURCE = (
    "package.json",
    "package-lock.json",
    "madar_update.py",
    "scripts/build_integrated_v123.py",
    "scripts/build_p0_release_candidate.py",
    "scripts/sync_font.py",
    "scripts/madar-update.iss",
    "scripts/Madar-Upgrade-Preflight.ps1",
    "scripts/Madar-Activate-Version.ps1",
    "scripts/qa_p0_v123_webview2.py",
    "native_app.py",
    "assets/madar.ico",
)
EXPECTED_ARTIFACTS = (
    "Madar-Desk-v1.0.23-Cumulative-20261107-SettingsTaraz.exe",
    "Madar-Desk-1.0.23-Setup-QA.exe",
    "Madar-Desk-1.0.23-Setup.exe",
    "Madar-Desk-1.0.23-Setup.release.json",
    "Madar-Desk-1.0.23-Setup-QA.acceptance.json",
)
EXPECTED_SIDECARS = tuple(
    name + ".sha256.txt" for name in EXPECTED_ARTIFACTS[:3]
)
_HEAD = re.compile(r"[0-9a-f]{40}\Z")
_AC = {f"AC-{n:02d}" for n in range(1, 33)}
_G = {f"G-{n:02d}" for n in range(1, 9)}
_GATES = _AC | _G
_ROW = re.compile(r"^\|\s*((?:AC|G)-\d{2})\s*\|", re.ASCII)


class UnsafeRoot(ValueError):
    """Reject path escapes/reparse points rather than reading linked files."""


def _reparse(path: Path) -> bool:
    if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
        return True
    try:
        attrs = getattr(path.lstat(), "st_file_attributes", 0)
        return bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    except FileNotFoundError:
        return False


def _no_links(path: Path) -> None:
    """Inspect every existing ancestor without following a link/junction."""
    for part in (path, *path.parents):
        if _reparse(part):
            raise UnsafeRoot("symlink_or_reparse_point")


def _root(value: str | None) -> tuple[Path, bool]:
    explicit = value is not None
    path = Path(value) if explicit else Path(__file__).absolute().parent.parent
    if not path.is_absolute() or path == Path(path.anchor):
        raise UnsafeRoot("absolute_non_drive_root_required")
    _no_links(path)
    if not path.is_dir():
        raise UnsafeRoot("root_is_not_a_directory")
    if explicit:
        marker = _inside(path, SYNTHETIC_MARKER)
        if not marker.is_file() or marker.stat().st_size > 1024:
            raise UnsafeRoot("explicit_root_requires_disposable_marker")
        try:
            content = json.loads(marker.read_text(encoding="utf-8"))
        except (UnicodeError, ValueError, OSError) as exc:
            raise UnsafeRoot("invalid_synthetic_marker") from exc
        if content != SYNTHETIC_OWNERSHIP:
            raise UnsafeRoot("invalid_synthetic_marker")
    return path, explicit


def _inside(root: Path, name: str) -> Path:
    """A fixed relative path only; refuse symlink ancestors and target."""
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise UnsafeRoot("path_escape")
    candidate = root.joinpath(*relative.parts)
    _no_links(candidate)
    return candidate


def _read_text(root: Path, name: str, *, max_bytes: int = 1024 * 1024) -> str:
    path = _inside(root, name)
    if not path.is_file() or path.stat().st_size > max_bytes:
        raise ValueError("required_file_missing_or_oversized")
    return path.read_text(encoding="utf-8")


def _version_assignment(source: str, attribute: str) -> list[str]:
    matches = []
    for node in ast.parse(source).body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (isinstance(target, ast.Name) and target.id == attribute) or (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and f"{target.value.id}.{target.attr}" == attribute
            ):
                if isinstance(node.value, ast.Constant) and type(node.value.value) is str:
                    matches.append(node.value.value)
                else:
                    matches.append("<nonliteral>")
    return matches


def _git(root: Path, *parts: str) -> str:
    env = os.environ.copy()
    env.update({
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_TERMINAL_PROMPT": "0",
    })
    result = subprocess.run(
        ["git", "--no-optional-locks", "-c", "core.fsmonitor=false",
         "-c", "submodule.recurse=false", "-C", str(root), *parts],
        capture_output=True, check=False, timeout=6, env=env,
        encoding="utf-8", errors="replace",
    )
    if result.returncode:
        raise ValueError("git_metadata_unavailable")
    return result.stdout.strip()


def _check_versions(root: Path) -> dict:
    try:
        package = json.loads(_read_text(root, "package.json"))
        lock = json.loads(_read_text(root, "package-lock.json", max_bytes=8 * 1024 * 1024))
        updater = _version_assignment(_read_text(root, "madar_update.py"),
                                      "CURRENT_VERSION")
        wrapper = _read_text(root, "scripts/build_integrated_v123.py")
        built = _version_assignment(wrapper, "builder.VERSION")
        package_version = package.get("version")
        lock_version = lock.get("version")
        lock_root = lock.get("packages", {}).get("", {}).get("version")
        route = package.get("scripts", {}).get("dist:rc")
        expected_route = ("python -B scripts/build_integrated_v123.py --webview2 "
                          + PREREQUISITE)
        values = (package_version, lock_version, lock_root)
        valid = (all(type(value) is str and value == EXPECTED_VERSION for value in values)
                 and updater == [EXPECTED_VERSION] and built == [EXPECTED_VERSION]
                 and route == expected_route)
        return {
            "state": "PASS" if valid else "BLOCKED",
            "package": package_version,
            "lock": lock_version,
            "lock_root": lock_root,
            "updater": updater,
            "wrapper": built,
            "dist_rc_matches_exact_entrypoint": route == expected_route,
        }
    except (OSError, ValueError, TypeError, KeyError, SyntaxError, AttributeError):
        return {"state": "UNKNOWN", "reason": "unreadable_or_invalid_source_metadata"}


def _check_git(root: Path, *, explicit_fixture: bool) -> dict:
    try:
        metadata = _inside(root, ".git")
        if explicit_fixture and not metadata.is_dir():
            return {"state": "UNKNOWN", "reason": "fixture_git_directory_required"}
        top = Path(_git(root, "rev-parse", "--show-toplevel"))
        _no_links(top)
        if os.path.normcase(os.path.abspath(top)) != os.path.normcase(os.path.abspath(root)):
            return {"state": "BLOCKED", "reason": "root_not_git_toplevel"}
        head = _git(root, "rev-parse", "--verify", "HEAD")
        if not _HEAD.fullmatch(head):
            return {"state": "UNKNOWN", "reason": "invalid_git_head"}
        status = _git(root, "status", "--porcelain=v1", "--untracked-files=normal")
        return {
            "state": "BLOCKED" if status else "PASS",
            "head": head,
            "dirty_or_untracked": bool(status),
            "change_count": len(status.splitlines()) if status else 0,
        }
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {"state": "UNKNOWN", "reason": "git_metadata_unavailable"}


def _check_prerequisite(root: Path) -> dict:
    try:
        path = _inside(root, PREREQUISITE)
        if not path.is_file() or path.stat().st_size <= 0:
            return {"state": "BLOCKED", "present": False}
        return {"state": "PASS", "present": True, "bytes": path.stat().st_size}
    except (OSError, UnsafeRoot):
        return {"state": "BLOCKED", "present": False, "reason": "unsafe_prerequisite_path"}


def _check_sources(root: Path) -> dict:
    missing, unsafe = [], []
    for name in REQUIRED_SOURCE:
        try:
            path = _inside(root, name)
            if not path.is_file():
                missing.append(name)
        except (OSError, UnsafeRoot):
            unsafe.append(name)
    return {
        "state": "BLOCKED" if missing or unsafe else "PASS",
        "missing": missing,
        "unsafe": unsafe,
        "note": "source_presence_only; installed toolchain availability unverified",
    }


def _check_collisions(root: Path) -> dict:
    names = [f"release/{name}" for name in EXPECTED_ARTIFACTS + EXPECTED_SIDECARS]
    names += [".qa-inno-v123-integrated", ".qa-p0-pyinstaller"]
    collisions, unsafe = [], []
    for name in names:
        try:
            if _inside(root, name).exists():
                collisions.append(name)
        except (OSError, UnsafeRoot):
            unsafe.append(name)
    return {
        "state": "BLOCKED" if collisions or unsafe else "PASS",
        "collisions": collisions, "unsafe": unsafe,
    }


def _check_acceptance(root: Path) -> dict:
    try:
        content = _read_text(
            root, "docs/modernization/MTR_E7_ACCEPTANCE_GATES_20261109.md")
        seen: dict[str, list[str]] = {}
        for line in content.splitlines():
            match = _ROW.match(line)
            if match:
                parts = [part.strip() for part in line.strip().strip("|").split("|")]
                seen.setdefault(match.group(1), []).append(parts[-1])
        missing = sorted(_GATES - set(seen))
        extra = sorted(set(seen) - _GATES)
        duplicates = sorted(key for key, values in seen.items() if len(values) != 1)
        unknown = sorted(key for key, values in seen.items()
                         if any(value not in {"OPEN"} for value in values))
        open_gates = sorted(key for key, values in seen.items()
                            if len(values) == 1 and values == ["OPEN"])
        complete = not (missing or extra or duplicates or unknown)
        return {
            "state": "BLOCKED" if complete else "UNKNOWN",
            "expected_total": 40,
            "open_count": len(open_gates),
            "missing": missing,
            "extra": extra,
            "duplicates": duplicates,
            "non_open_or_unrecognized": unknown,
            "note": "documentation_only; OPEN is a release blocker",
        }
    except (OSError, ValueError, UnsafeRoot, UnicodeError):
        return {"state": "UNKNOWN", "reason": "acceptance_matrix_unreadable"}


def audit(root: Path, *, explicit_fixture: bool) -> dict:
    checks = {
        "version_triad": _check_versions(root),
        "source_git": _check_git(root, explicit_fixture=explicit_fixture),
        "webview2_offline_file": _check_prerequisite(root),
        "webview2_authenticode": {
            "state": "UNKNOWN",
            "reason": "signature_not_checked; static_presence_is_not_proof",
        },
        "webview2_full_offline_identity": {
            "state": "UNKNOWN",
            "reason": "full_offline_installer_not_authenticated",
        },
        "builder_sources": _check_sources(root),
        "installed_toolchain": {
            "state": "UNKNOWN",
            "reason": "PyInstaller_Node_Inno_and_fonts_not_executed_or_verified",
        },
        "artifact_collisions": _check_collisions(root),
        "acceptance_ac_g": _check_acceptance(root),
    }
    try:
        dist = _inside(root, "dist/index.html").is_file()
        checks["dist"] = {
            "state": "UNKNOWN",
            "present": dist,
            "reason": "existing_dist_is_not_a_release_provenance_or_freshness_gate",
        }
    except (OSError, UnsafeRoot):
        checks["dist"] = {"state": "BLOCKED", "reason": "unsafe_dist_path"}
    blockers = [name for name, value in checks.items() if value["state"] != "PASS"]
    return {
        "schema": 1,
        "tool": "mtr_release_readiness",
        "read_only": True,
        "mode": "disposable_fixture" if explicit_fixture else "source_worktree",
        "root": str(root),
        "decision": "NO_GO" if blockers else "GO",
        "may_build": not blockers,
        "may_install": False,
        "may_distribute": False,
        "blockers": blockers,
        "checks": checks,
        "limitation": ("Static metadata cannot attest WebView2 signing/offline identity, "
                       "installed toolchain, physical Windows/WebView2, financial "
                       "acceptance, package contents, installer rollback or release."),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", help="absolute disposable synthetic fixture directory")
    args = parser.parse_args(argv)
    try:
        path, explicit = _root(args.root)
        report = audit(path, explicit_fixture=explicit)
    except (OSError, UnsafeRoot, ValueError) as exc:
        report = {
            "schema": 1,
            "tool": "mtr_release_readiness",
            "read_only": True,
            "decision": "NO_GO",
            "may_build": False,
            "may_install": False,
            "may_distribute": False,
            "blockers": ["unsafe_or_unavailable_root"],
            "checks": {"root": {"state": "BLOCKED", "reason": str(exc)}},
        }
    except Exception as exc:
        # The machine-readable fail-closed contract also covers unexpected
        # parsing/tooling bugs. Do not expose local paths or stack traces.
        report = {
            "schema": 1,
            "tool": "mtr_release_readiness",
            "read_only": True,
            "decision": "NO_GO",
            "may_build": False,
            "may_install": False,
            "may_distribute": False,
            "blockers": ["preflight_internal_error"],
            "checks": {"preflight": {
                "state": "UNKNOWN", "reason": type(exc).__name__,
            }},
        }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if report["may_build"] else 2


if __name__ == "__main__":
    sys.exit(main())
