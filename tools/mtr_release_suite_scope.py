"""Explicit, review-gated Madar E0-E7 full-QA scope classifier.

This does NOT revise, delete, or mark historical tests as passing. The
full-suite report remains failed. All reviewed retired in-Madar accounting
modules are enumerated and source fingerprinted; all other failures remain
current blockers or unknown failures, never silently filtered.

Optional --run-current uses modernization_python_suite.execute_module with
disposable profiles. It is a SEPARATE result, never a replacement for the
original full-suite result. Running the full scope can include synthetic
loopback HTTP tests; use --known-failures-only for the isolated E2 test.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from unittest.mock import patch

from modernization_python_suite import PROJECT, execute_module
from safe_test_runner import isolated_environment


HISTORICAL_REPORT = Path(r"D:\CoS-Test\MTR_E0_E7_fullqa_20261110_afterfix.json")
PACKAGED_EXE_TEST = "test_packaged_madar_host_exe.py"
KNOWN_CURRENT_FAILURES = frozenset({"test_mtr_e2_recovery_security_20261110.py"})
# A legacy RC installer test would execute an existing binary if present. It
# belongs to separately authorized real-install acceptance, not source QA.
# Its reviewed bytes are pinned so changing its meaning reopens the decision.
REVIEWED_RELEASE_ONLY_SOURCES = {
    "test_release_portable_install.py":
        "000f3c35292401ca7029c6ab232e02e00d7bf43efd3bf9c1ec26debea8274f56",
}
DETACHED_TARAZ_WORKTREE = Path(
    r"D:\CoS-Test\000- Taraz\taraz-mtr-e2-isolated-20261109"
)
CROSS_SOURCE_INTEROP_MODULES = frozenset({
    "test_mtr_e2_cross_app.py",
    "test_mtr_e2_host_peer_pilot.py",
    "test_mtr_e2_signed_peer_registry_cross_app.py",
    "test_mtr_e2_two_source_https_pilot.py",
    "test_mtr_e4_local_catalog_pilot.py",
})

# Explicitly reviewed from the 2026-11-10 full-QA report AND test source.
# The SHA-256 fingerprint prevents silently exempting a source that changed
# since its accounting/retired-endpoint classification was reviewed.
REVIEWED_RETIRED_SOURCES = {
    "test_accounting_bridge.py": "2538e82b1b0e8eba7fabaa79cda3b7508890b0b7c5eb7b20a937dbae818d1b63",
    "test_authenticated_intake_cas.py": "5ad8e202ca08e2960469bbb90b22b60a1a58accf8a90c9bd44fade3a7090c36a",
    "test_card_trash_contract.py": "965532f25a33881f84b5116c9bf1ce9cc14c617a17f9f245cca5e9666b548181",
    "test_finance_bridge.py": "9bad568cf8c9d4ca68ccbf8d43b496dafa0649d3429e19b104ea434fe0ac6f61",
    "test_finance_overview.py": "e6645f060baa613fe932669ef5860837c8cc5284579cf660f05cb355ff35457f",
    "test_finance_reference_bridge.py": "7c90bab9b631c4eed26372f20407ad7fee7f759ab795fc1e1a260111c3c98855",
    "test_list_archive_contract.py": "a74e7470cd0f44f10b83663632d704d3531375fbdb00b45091cefd32e0484a78",
    "test_new_http_endpoints.py": "fbc0f905b63280bfcfa5e4fcd2df49824a259a9f547d0897d2cf2b6f7992ff90",
    "test_purchase_host_adversarial.py": "7eadf209d7694f2e12ac48e5f4ad9166d2e6d3a081c7e5832630a7fbdb7d63a0",
    "test_purchase_intake.py": "1880eb83c88500071b91f2f2d381ae1a4ceff9715063f1eec6651d23f587ada3",
    "test_release_lan.py": "b2f736809203ec6b26b2c43a0a5889076bbc5141d5acf3144045bf256e52ad97",
    "test_release_persistence.py": "a068e2795b8c1a59a4cb04a6fa6d5c253d097859063f4316d375dccf7ccd0e0a",
    "test_rial_host_read_bridge.py": "d48c115d7473443dd04845b81de3258771215300066d359dcbe2bc015177fc46",
    "test_rial_host_security_invariants.py": "1537fbcb75b9336d4e21369f7d7e105ed2ae322e8b17d066d93d007fa2759841",
    "test_rial_purchase_host_integration.py": "f67fb365f77e34ae3b5b055b2037dce3c4c8cf01bb4bbf7fe96fdb44f90333de",
    "test_sqlite_export_bridge.py": "e2f32dfc0c3a9e71365ea300728c1248f9e1426bdb26479a2f31074022c15b8d",
    "test_standalone_accounting_end_to_end.py": "c284856de3aba32450db9bc31505ffb5ef1f5d633be42d7aafe68f620322d647",
    "test_standalone_accounting_host.py": "c3b12a84e033b26bdda81ce9a5196fb9a27dcdf05ae66df4591022b2f36fd244",
    "test_standalone_task_prepare.py": "02cdb6c8636f44ac3c83106d343fbac97f4f4b86ca72f479fdb6123ecb2bd551",
    "test_unified_bridge.py": "54b29bf5c609dc4c550d23b8504f2a39a7550345100c5c45aafa7a1ee1a992a6",
    "test_user_acceptance_workflows.py": "19354b35ede90a03fc3eba1a091266b215eb30a47be1b8e75db3d0cfdd003e8a",
}

# A reviewed test must actually exercise the now-retired in-Madar financial
# API, not merely have an evocative filename. These source tokens were seen in
# the tests and cross-checked with native_app._retired_financial_method and
# the retired HTTP routes. The SHA above guards any later source change.
RETIRED_TEST_MARKERS = {
    "test_card_trash_contract.py": "financeCommand",
    "test_list_archive_contract.py": "financeCommand",
    "test_new_http_endpoints.py": "/api/finance",
    "test_release_lan.py": "/api/finance",
    "test_standalone_accounting_end_to_end.py": "standalone",
    "test_standalone_accounting_host.py": "standalone",
    "test_standalone_task_prepare.py": "standalone",
}
_DEFAULT_MARKERS = ("accountingCommand", "accountingRead", "financeCommand",
                    "finance_read", "/api/finance", "/api/rial")
_DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


class ScopeRefused(ValueError):
    """Missing evidence, unreviewed failure or unauthorized test exclusion."""


# This gate measures the project's executable source and release metadata,
# including untracked files and the 21 historical tests. Only dependency/tool
# caches and virtual environments are omitted, not Python/JS/React/PowerShell
# sources or versioned package manifests. Git-untracked files remain included.
SOURCE_SNAPSHOT_IGNORED_DIRS = frozenset({
    ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".tox", ".nox", ".venv", "venv", "node_modules",
})
SOURCE_SNAPSHOT_SUFFIXES = frozenset({
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".css",
    ".ps1", ".iss", ".html", ".json", ".yaml", ".yml", ".toml", ".ini",
})
_SOURCE_MAX_FILES = 12000
_SOURCE_MAX_DIRECTORIES = 20000
_SOURCE_MAX_ENTRIES = 150000
_SOURCE_MAX_SINGLE_BYTES = 32 * 1024 * 1024
_SOURCE_MAX_TOTAL_BYTES = 512 * 1024 * 1024
_SOURCE_READ_CHUNK = 256 * 1024
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def _source_is_alias(info: os.stat_result) -> bool:
    return (stat.S_ISLNK(info.st_mode) or
            bool(getattr(info, "st_file_attributes", 0) & _REPARSE_POINT))


def _source_file_sha(path: Path, initial: os.stat_result) -> str:
    """Bounded, no-follow read and metadata check across a single SHA-256 pass."""
    if _source_is_alias(initial) or not stat.S_ISREG(initial.st_mode):
        raise ScopeRefused("unsafe source file alias")
    if initial.st_size > _SOURCE_MAX_SINGLE_BYTES:
        raise ScopeRefused("source file exceeds snapshot safety bound")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        if (not stat.S_ISREG(opened.st_mode) or _source_is_alias(opened)
                or (initial.st_dev, initial.st_ino, initial.st_size,
                    initial.st_mtime_ns) !=
                   (opened.st_dev, opened.st_ino, opened.st_size,
                    opened.st_mtime_ns)):
            raise ScopeRefused("source changed or redirected during snapshot")
        sha = hashlib.sha256()
        length = 0
        with os.fdopen(fd, "rb", closefd=False) as handle:
            while True:
                chunk = handle.read(_SOURCE_READ_CHUNK)
                if not chunk:
                    break
                length += len(chunk)
                if length > _SOURCE_MAX_SINGLE_BYTES:
                    raise ScopeRefused("source grew beyond snapshot safety bound")
                sha.update(chunk)
        final_fd = os.fstat(fd)
    finally:
        os.close(fd)
    final_path = path.lstat()
    if (_source_is_alias(final_path) or
            not stat.S_ISREG(final_path.st_mode) or
            (initial.st_dev, initial.st_ino, initial.st_size, initial.st_mtime_ns)
            != (final_fd.st_dev, final_fd.st_ino, final_fd.st_size,
                final_fd.st_mtime_ns) or
            (initial.st_dev, initial.st_ino, initial.st_size, initial.st_mtime_ns)
            != (final_path.st_dev, final_path.st_ino, final_path.st_size,
                final_path.st_mtime_ns) or length != initial.st_size):
        raise ScopeRefused("source changed during snapshot")
    return sha.hexdigest()


def capture_source_snapshot(root: Path) -> dict:
    """Bounded repo-wide source/metadata inventory with content SHA-256.

    Reject symlinks, junctions and other reparse points inside the scanned
    tree, including directories which could hide source outside the root.
    This measures two checkpoints, NOT every instant in between them.
    """
    if not isinstance(root, Path) or not root.is_absolute():
        raise ScopeRefused("absolute source snapshot root required")
    root_info = root.lstat()
    if _source_is_alias(root_info) or not stat.S_ISDIR(root_info.st_mode):
        raise ScopeRefused("unsafe source snapshot root")
    stack = [(root, "", root_info)]
    files = {}
    total_bytes = 0
    directories = 0
    entries_seen = 0
    while stack:
        folder, relative, expected_folder = stack.pop()
        # Re-check before descending: an untrusted directory must not be
        # substituted by a junction after its parent was enumerated.
        folder_info = folder.lstat()
        if (_source_is_alias(folder_info) or
                not stat.S_ISDIR(folder_info.st_mode) or
                (folder_info.st_dev, folder_info.st_ino) !=
                (expected_folder.st_dev, expected_folder.st_ino)):
            raise ScopeRefused("source directory changed or became unsafe")
        directories += 1
        if directories > _SOURCE_MAX_DIRECTORIES:
            raise ScopeRefused("source directory inventory bound exceeded")
        # scandir deliberately sees untracked and uncommitted files; git ls-files
        # would silently omit both. Do not recursively follow directory links.
        with os.scandir(folder) as children:
            for entry in children:
                entries_seen += 1
                if entries_seen > _SOURCE_MAX_ENTRIES:
                    raise ScopeRefused("source directory entry inventory bound exceeded")
                name = entry.name
                rel = name if not relative else relative + "/" + name
                details = entry.stat(follow_symlinks=False)
                if _source_is_alias(details):
                    raise ScopeRefused("unsafe source symlink/reparse path: " + rel)
                if stat.S_ISDIR(details.st_mode):
                    if name.casefold() not in SOURCE_SNAPSHOT_IGNORED_DIRS:
                        child = Path(entry.path)
                        child_info = child.lstat()
                        if (_source_is_alias(child_info) or
                                not stat.S_ISDIR(child_info.st_mode)):
                            raise ScopeRefused("unsafe source directory path: " + rel)
                        stack.append((child, rel, child_info))
                elif stat.S_ISREG(details.st_mode):
                    if Path(name).suffix.casefold() not in SOURCE_SNAPSHOT_SUFFIXES:
                        continue
                    source_path = Path(entry.path)
                    # On Windows, DirEntry.stat() can return st_ino=st_dev=0
                    # while fstat()/Path.lstat() return actual file identities.
                    initial = source_path.lstat()
                    if (_source_is_alias(initial) or
                            not stat.S_ISREG(initial.st_mode) or
                            initial.st_size != details.st_size):
                        raise ScopeRefused("source changed or redirected during scan")
                    if len(files) >= _SOURCE_MAX_FILES:
                        raise ScopeRefused("source file inventory bound exceeded")
                    total_bytes += initial.st_size
                    if total_bytes > _SOURCE_MAX_TOTAL_BYTES:
                        raise ScopeRefused("source byte inventory bound exceeded")
                    files[rel] = _source_file_sha(source_path, initial)
                elif Path(name).suffix.casefold() in SOURCE_SNAPSHOT_SUFFIXES:
                    raise ScopeRefused("nonregular source file: " + rel)
    if not files:
        raise ScopeRefused("empty source inventory")
    source_list = [[name, digest] for name, digest in sorted(files.items())]
    fingerprint = hashlib.sha256(json.dumps(
        source_list, ensure_ascii=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    return {
        "fingerprintSha256": fingerprint,
        "fileCount": len(files),
        "totalBytes": total_bytes,
        "files": files,
    }


def require_unchanged_source_snapshot(before: dict, after: dict) -> None:
    """Fail closed for content mutation, addition, deletion or path rebind."""
    if before["fingerprintSha256"] == after["fingerprintSha256"] and (
            before["files"] == after["files"]):
        return
    prior, latest = before["files"], after["files"]
    added = sorted(set(latest) - set(prior))
    deleted = sorted(set(prior) - set(latest))
    changed = sorted(name for name in set(prior) & set(latest)
                     if prior[name] != latest[name])
    # Bounded diagnostic to avoid flooding stdout/stderr or copying source.
    preview = ",".join((["+" + n for n in added[:3]] +
                        ["-" + n for n in deleted[:3]] +
                        ["~" + n for n in changed[:3]]))[:500]
    raise ScopeRefused(
        "source snapshot changed during current-scope run"
        f" (added={len(added)}, deleted={len(deleted)}, modified={len(changed)}): "
        + preview
    )


def retired_set_digest() -> str:
    canonical = json.dumps(REVIEWED_RETIRED_SOURCES, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _nonnegative_int(value, label):
    if type(value) is not int or value < 0:
        raise ScopeRefused("invalid full QA counter: " + label)
    return value


def _source_checks(test_dir: Path) -> None:
    if len(REVIEWED_RETIRED_SOURCES) != 21:
        raise ScopeRefused("reviewed retired set must contain exactly 21 modules")
    if set(RETIRED_TEST_MARKERS) - set(REVIEWED_RETIRED_SOURCES):
        raise ScopeRefused("retirement source marker does not match reviewed set")
    for name, expected in sorted(REVIEWED_RETIRED_SOURCES.items()):
        if (Path(name).name != name or not name.startswith("test_")
                or not name.endswith(".py") or not _DIGEST_PATTERN.fullmatch(expected)):
            raise ScopeRefused("invalid reviewed module or source SHA")
        path = test_dir / name
        if not path.is_file() or path.is_symlink():
            raise ScopeRefused("retired test source absent/unsafe: " + name)
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ScopeRefused("retired test source changed; re-review required: " + name)
        source = raw.decode("utf-8")
        expected_markers = (
            (RETIRED_TEST_MARKERS[name],) if name in RETIRED_TEST_MARKERS
            else _DEFAULT_MARKERS
        )
        if not any(marker in source for marker in expected_markers):
            raise ScopeRefused("retired financial test evidence absent: " + name)
    # Need independent code evidence that these APIs were intentionally retired.
    production = test_dir.parent / "native_app.py"
    if not production.is_file():
        raise ScopeRefused("retirement source boundary absent")
    body = production.read_text(encoding="utf-8")
    if ("def _retired_financial_method" not in body or
            "setattr(Bridge, _retired_method, _retired_financial_method)" not in body):
        raise ScopeRefused("retired host financial method boundary not found")


def classify_full_report(report: dict, test_dir: Path) -> dict:
    """Verify report truth and test-source review; never recompute away failures."""
    if type(report) is not dict or type(report.get("modules")) is not list:
        raise ScopeRefused("invalid full QA report")
    summary = report.get("summary")
    if type(summary) is not dict:
        raise ScopeRefused("full QA summary absent")
    _source_checks(test_dir)
    rows = report["modules"]
    names = []
    counts = {"pass": 0, "fail": 0, "timeout": 0}
    for row in rows:
        if type(row) is not dict:
            raise ScopeRefused("invalid full QA module row")
        name = row.get("module")
        status = row.get("status")
        if (type(name) is not str or Path(name).name != name or
                not name.startswith("test_") or not name.endswith(".py") or
                status not in counts):
            raise ScopeRefused("unrecognized module identity or status")
        names.append(name)
        counts[status] += 1
        for field in ("failures", "errors"):
            _nonnegative_int(row.get(field), name + "." + field)
        if status == "pass" and (row["failures"] or row["errors"]):
            raise ScopeRefused("passing row reports errors/assertions")
        if status == "fail" and row.get("returncode") == 0:
            raise ScopeRefused("failed row contradicts exit code")
    if len(set(names)) != len(names) or not rows:
        raise ScopeRefused("duplicate/empty full QA module inventory")
    if not set(REVIEWED_RETIRED_SOURCES) <= set(names):
        raise ScopeRefused("one or more reviewed retired modules missing from full QA")
    excluded = summary.get("modules_excluded")
    if type(excluded) is not list or set(excluded) != {PACKAGED_EXE_TEST}:
        raise ScopeRefused("historical full QA has unexpected hidden exclusions")
    expected_counts = {
        "modules_executed": len(rows),
        "modules_passed": counts["pass"],
        "modules_failed": counts["fail"],
        "modules_timed_out": counts["timeout"],
        "test_failures": sum(r["failures"] for r in rows),
        "test_errors": sum(r["errors"] for r in rows),
    }
    for key, expected in expected_counts.items():
        if _nonnegative_int(summary.get(key), key) != expected:
            raise ScopeRefused("original full QA report inconsistent: " + key)
    if (_nonnegative_int(summary.get("modules_discovered"), "modules_discovered")
            != len(rows) + len(excluded)):
        raise ScopeRefused("original full QA discovered/ran counts disagree")

    failing = {r["module"] for r in rows if r["status"] != "pass"}
    retired = sorted(REVIEWED_RETIRED_SOURCES)
    retired_failed = sorted(failing & set(retired))
    active_failed = sorted(failing - set(retired))
    unknown_failed = sorted(set(active_failed) - KNOWN_CURRENT_FAILURES)
    retired_rows = [r for r in rows if r["module"] in REVIEWED_RETIRED_SOURCES]
    return {
        "historicalFullSuitePassed": counts["fail"] == counts["timeout"] == 0,
        "historicalFullSuite": dict(summary),
        "retiredAccountingModulesCount": len(retired),
        "retiredAccountingModuleNames": retired,
        "retiredAccountingFailedModuleNames": retired_failed,
        "retiredAccountingHistoricalAssertions": sum(r["failures"] for r in retired_rows),
        "retiredAccountingHistoricalErrors": sum(r["errors"] for r in retired_rows),
        "currentArchitectureHistoricalFailedModuleNames": active_failed,
        "currentArchitectureHistoricalFailureDetails": [
            {"module": r["module"], "status": r["status"],
             "assertions": r["failures"], "errors": r["errors"]}
            for r in rows if r["module"] in active_failed
        ],
        "unknownFailedModules": unknown_failed,
        "historicalExecutedModuleNames": sorted(names),
        "reviewedRetiredSetSha256": retired_set_digest(),
        "reportIncludesExplicitPackagedExeExclusion": True,
        "readinessVerdict": (
            "BLOCKED_UNKNOWN_FAILURE" if unknown_failed else
            "BLOCKED_CURRENT_FAILURE" if active_failed else
            "BLOCKED_RETIRED_SCOPE_NOT_FULL_SUITE_PASS"
            if retired_failed else "HISTORICAL_FULL_SUITE_PASS"
        ),
    }


def current_modules(test_dir: Path, classification: dict, *, known_only: bool) -> list[Path]:
    """No name outside the exact reviewed set is silently excluded."""
    source_paths = sorted(test_dir.glob("test_*.py"))
    if any(p.is_symlink() or not p.is_file() for p in source_paths):
        raise ScopeRefused("unsafe current test module path")
    names = {p.name for p in source_paths}
    if not set(REVIEWED_RETIRED_SOURCES) <= names:
        raise ScopeRefused("reviewed retired module missing before current run")
    if not set(REVIEWED_RELEASE_ONLY_SOURCES) <= names:
        raise ScopeRefused("reviewed release-only installer test missing")
    for name, expected in REVIEWED_RELEASE_ONLY_SOURCES.items():
        if hashlib.sha256((test_dir / name).read_bytes()).hexdigest() != expected:
            raise ScopeRefused("reviewed release-only installer source changed")
    if classification["unknownFailedModules"]:
        raise ScopeRefused("new/unknown historical failure requires explicit review")
    if known_only:
        wanted = set(classification["currentArchitectureHistoricalFailedModuleNames"])
        if not wanted or not wanted <= KNOWN_CURRENT_FAILURES or not wanted <= names:
            raise ScopeRefused("no reviewed currently failing module to re-run")
    else:
        wanted = (names - set(REVIEWED_RETIRED_SOURCES)
                  - {PACKAGED_EXE_TEST} - set(REVIEWED_RELEASE_ONLY_SOURCES))
    if (PACKAGED_EXE_TEST in wanted or wanted & set(REVIEWED_RETIRED_SOURCES)
            or wanted & set(REVIEWED_RELEASE_ONLY_SOURCES)):
        raise ScopeRefused("invalid current scope selection")
    return [p for p in source_paths if p.name in wanted]


def validate_detached_taraz_source(source: Path | None) -> Path | None:
    """Pin cross-source tests to the owner-designated detached Taraz worktree.

    An arbitrary environment variable is not an authority to load Python from
    another directory. The caller must explicitly select this source for QA.
    """
    if source is None:
        return None
    if not isinstance(source, Path) or not source.is_absolute():
        raise ScopeRefused("detached Taraz source must be an explicit absolute path")
    try:
        if source.resolve(strict=True) != DETACHED_TARAZ_WORKTREE.resolve(strict=True):
            raise ScopeRefused("Taraz source is not the reviewed detached worktree")
        for directory in (source, source.parent, source.parent.parent):
            info = directory.lstat()
            if _source_is_alias(info) or not stat.S_ISDIR(info.st_mode):
                raise ScopeRefused("unsafe detached Taraz directory alias")
        if not (source / ".git").exists():
            raise ScopeRefused("Taraz worktree marker missing")
        for name in ("taraz_mtr_peer_registry.py", "taraz_mtr_peer_http.py",
                     "taraz_mtr_catalog_read.py", "taraz_integration.py"):
            candidate = source / name
            info = candidate.lstat()
            if _source_is_alias(info) or not stat.S_ISREG(info.st_mode):
                raise ScopeRefused("unsafe detached Taraz source module")
    except (OSError, RuntimeError) as exc:
        raise ScopeRefused("detached Taraz source unavailable or unsafe") from exc
    return source.resolve(strict=True)


def run_current_scope(
    test_dir: Path, classification: dict, *, reviewed_digest: str,
    known_only: bool = False, workers: int = 2, timeout: int = 120,
    taraz_source: Path | None = None,
) -> dict:
    if type(reviewed_digest) is not str or reviewed_digest != retired_set_digest():
        raise ScopeRefused("explicit reviewed retirement-set SHA-256 acknowledgment required")
    if test_dir.resolve() != (PROJECT / "tests").resolve():
        raise ScopeRefused("current execution must use the actual reviewed project tests")
    if not 1 <= workers <= 4 or not 1 <= timeout <= 179:
        raise ScopeRefused("workers must be 1..4 and timeout 1..179")
    paths = current_modules(test_dir, classification, known_only=known_only)
    if not paths:
        raise ScopeRefused("no current-scope modules to run")
    selected_taraz = validate_detached_taraz_source(taraz_source)
    cross_source = {p.name for p in paths} & CROSS_SOURCE_INTEROP_MODULES
    if cross_source and selected_taraz is None:
        raise ScopeRefused("explicit detached Taraz source required for current interop QA")
    before_source = capture_source_snapshot(PROJECT)
    before_taraz = (capture_source_snapshot(selected_taraz)
                    if selected_taraz is not None else None)
    # Guard the otherwise invisible gap between test selection and initial
    # fingerprint. A new test in that gap must be selected or the run aborts.
    if ([path.name for path in current_modules(
            test_dir, classification, known_only=known_only)]
            != [path.name for path in paths]):
        raise ScopeRefused("current test inventory changed before suite execution")
    with tempfile.TemporaryDirectory(prefix="madar-e0-e7-current-scope-") as root:
        scratch = Path(root)
        parent_env = isolated_environment(scratch / "parent")
        # The inherited environment must never silently select unreviewed code.
        parent_env.pop("MTR_TARAZ_SOURCE", None)
        if selected_taraz is not None:
            parent_env["MTR_TARAZ_SOURCE"] = str(selected_taraz)
        with patch.dict(os.environ, parent_env, clear=True):
            with ThreadPoolExecutor(max_workers=workers) as pool:
                jobs = {pool.submit(execute_module, path, scratch / "modules",
                                    timeout, False): path.name for path in paths}
                results = []
                for job in as_completed(jobs):
                    result = job.result()
                    if result.get("module") != jobs[job]:
                        raise ScopeRefused("module execution result changed identity")
                    results.append(result)
                    print("CURRENT_SCOPE_MODULE " + json.dumps({
                        "module": result["module"], "status": result["status"],
                        "tests": result["tests"], "errors": result["errors"],
                        "assertions": result["failures"],
                    }, ensure_ascii=True), flush=True)
    after_source = capture_source_snapshot(PROJECT)
    require_unchanged_source_snapshot(before_source, after_source)
    if before_taraz is not None:
        require_unchanged_source_snapshot(
            before_taraz, capture_source_snapshot(selected_taraz))
    if ([path.name for path in current_modules(
            test_dir, classification, known_only=known_only)]
            != [path.name for path in paths]):
        raise ScopeRefused("current test inventory changed during suite execution")
    results.sort(key=lambda row: row["module"])
    unexecuted = [r["module"] for r in results if r["status"] == "pass" and (
        type(r.get("tests")) is not int or r["tests"] < 1 or
        type(r.get("skipped", 0)) is not int or
        not 0 <= r.get("skipped", 0) < r["tests"]
    )]
    if unexecuted:
        raise ScopeRefused("zero-test, all-skipped or uncounted passing module(s): "
                           + ", ".join(unexecuted))
    return {
        "scope": ("TARGETED_KNOWN_FAILURES_ONLY_NOT_RELEASE_QA" if known_only
                  else "EXPLICIT_CURRENT_SOURCE_SCOPE_NOT_FULL_SUITE_QA"),
        "historicalFullSuitePassed": classification["historicalFullSuitePassed"],
        "historicalFullSuiteErrors": classification["historicalFullSuite"]["test_errors"],
        "historicalFullSuiteAssertions": classification["historicalFullSuite"]["test_failures"],
        "retiredModuleNames": classification["retiredAccountingModuleNames"],
        "excludedReleaseOnlyModuleNames": sorted(
            {PACKAGED_EXE_TEST, *REVIEWED_RELEASE_ONLY_SOURCES}),
        "sourceSnapshotSha256": before_source["fingerprintSha256"],
        "sourceSnapshotFiles": before_source["fileCount"],
        "sourceSnapshotBytes": before_source["totalBytes"],
        "sourceSnapshotMatchedPrePost": True,
        "sourceSnapshotExcludedDirectories": sorted(SOURCE_SNAPSHOT_IGNORED_DIRS),
        "detachedTarazSourceSha256": (
            before_taraz["fingerprintSha256"] if before_taraz else None),
        "detachedTarazSourceFiles": before_taraz["fileCount"] if before_taraz else 0,
        "detachedTarazSourceMatchedPrePost": before_taraz is not None,
        "executed": len(results),
        "passed": sum(r["status"] == "pass" for r in results),
        "failed": sum(r["status"] == "fail" for r in results),
        "timedOut": sum(r["status"] == "timeout" for r in results),
        "unknownTestModuleNamesSinceReport": sorted(
            {p.name for p in paths}
            - set(classification["historicalExecutedModuleNames"])
        ),
        "modules": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical-report", type=Path, default=HISTORICAL_REPORT)
    parser.add_argument("--test-dir", type=Path, default=PROJECT / "tests")
    parser.add_argument("--run-current", action="store_true",
                        help="Explicit current suite with disposable profiles")
    parser.add_argument("--known-failures-only", action="store_true",
                        help="Run known current failures only; NEVER a release pass")
    parser.add_argument("--approve-retired-sha256",
                        help="Exact digest printed in classification; mandatory for rerun")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--taraz-source", type=Path,
                        help="Explicit reviewed detached Taraz worktree for cross-source QA")
    args = parser.parse_args(argv)
    try:
        if args.known_failures_only and not args.run_current:
            raise ScopeRefused("--known-failures-only requires --run-current")
        report_bytes = args.historical_report.read_bytes()
        report = json.loads(report_bytes.decode("utf-8"))
        classification = classify_full_report(report, args.test_dir)
        classification["historicalReportSha256"] = hashlib.sha256(report_bytes).hexdigest()
        # Inventory remains available internally to detect modules added since
        # the historical run; do not flood operational output with 249 pass IDs.
        printable = {k: v for k, v in classification.items()
                     if k != "historicalExecutedModuleNames"}
        print("HISTORICAL_FULL_QA " + json.dumps(printable, ensure_ascii=True),
              flush=True)
        if classification["unknownFailedModules"]:
            print("SCOPE_BLOCKED unknown failed module(s) are not retired or reviewed",
                  file=sys.stderr, flush=True)
            return 2
        if not args.run_current:
            # Audit itself is valid, but known E2 failure and the full-suite
            # 118 errors/9 assertions remain real release blockers.
            return 1 if not classification["historicalFullSuitePassed"] else 0
        result = run_current_scope(
            args.test_dir, classification, reviewed_digest=args.approve_retired_sha256,
            known_only=args.known_failures_only, workers=args.workers,
            timeout=args.timeout,
            taraz_source=args.taraz_source,
        )
        print("CURRENT_SCOPE_QA " + json.dumps(result, ensure_ascii=True), flush=True)
        return 0 if result["executed"] == result["passed"] else 1
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        print("SCOPE_BLOCKED " + str(exc).encode("ascii", "backslashreplace").decode(),
              file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
