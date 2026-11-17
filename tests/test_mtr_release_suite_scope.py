"""QA classifier contracts using actual 2026-11-10 full-QA plus synthetic mutations.

No production writes, network services, real profiles, historical test edits
or child test-module runs. The CLI's optional execution is separately gated.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))

from mtr_release_suite_scope import (  # noqa: E402
    HISTORICAL_REPORT, KNOWN_CURRENT_FAILURES, PACKAGED_EXE_TEST,
    REVIEWED_RELEASE_ONLY_SOURCES,
    REVIEWED_RETIRED_SOURCES, ScopeRefused, classify_full_report,
    capture_source_snapshot, current_modules, main, retired_set_digest,
    require_unchanged_source_snapshot, run_current_scope,
    validate_detached_taraz_source,
)


class MtrReleaseScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.historical = json.loads(HISTORICAL_REPORT.read_text(encoding="utf-8"))
        cls.test_dir = PROJECT / "tests"

    def classify(self, report=None, test_dir=None):
        return classify_full_report(
            deepcopy(self.historical) if report is None else report,
            self.test_dir if test_dir is None else test_dir,
        )

    def test_actual_full_qa_counters_21_reviewed_and_current_failure_are_visible(self):
        result = self.classify()
        full = result["historicalFullSuite"]
        self.assertFalse(result["historicalFullSuitePassed"])
        self.assertEqual((
            full["modules_discovered"], full["modules_executed"],
            full["modules_passed"], full["modules_failed"],
            full["test_errors"], full["test_failures"],
        ), (250, 249, 227, 22, 118, 9))
        self.assertEqual(result["retiredAccountingModulesCount"], 21)
        self.assertEqual(
            set(result["retiredAccountingModuleNames"]),
            set(REVIEWED_RETIRED_SOURCES),
        )
        self.assertEqual(len(result["retiredAccountingFailedModuleNames"]), 21)
        self.assertEqual(result["retiredAccountingHistoricalErrors"], 117)
        self.assertEqual(result["retiredAccountingHistoricalAssertions"], 9)
        self.assertEqual(result["currentArchitectureHistoricalFailedModuleNames"],
                         ["test_mtr_e2_recovery_security_20261110.py"])
        self.assertEqual(result["currentArchitectureHistoricalFailureDetails"],
                         [{"module": "test_mtr_e2_recovery_security_20261110.py",
                           "status": "fail", "assertions": 0, "errors": 1}])
        self.assertEqual(result["unknownFailedModules"], [])
        self.assertEqual(result["readinessVerdict"], "BLOCKED_CURRENT_FAILURE")
        self.assertEqual(full["modules_excluded"], [PACKAGED_EXE_TEST])

    def test_new_unreviewed_failing_module_is_reported_and_blocks_any_run(self):
        report = deepcopy(self.historical)
        passing = next(row for row in report["modules"]
                       if row["status"] == "pass"
                       and row["module"] not in REVIEWED_RETIRED_SOURCES)
        unreviewed = passing["module"]
        passing.update(status="fail", returncode=1, errors=1,
                       diagnostic="synthetic current failure")
        report["summary"]["modules_passed"] -= 1
        report["summary"]["modules_failed"] += 1
        report["summary"]["test_errors"] += 1
        result = self.classify(report)
        self.assertEqual(result["unknownFailedModules"], [unreviewed])
        self.assertFalse(result["historicalFullSuitePassed"])
        with patch("mtr_release_suite_scope.execute_module") as runner:
            with self.assertRaisesRegex(ScopeRefused, "unknown"):
                run_current_scope(self.test_dir, result,
                                  reviewed_digest=retired_set_digest(),
                                  known_only=False)
        runner.assert_not_called()

    def test_new_failure_row_cannot_be_hidden_by_keeping_original_summary(self):
        report = deepcopy(self.historical)
        report["modules"].append({
            "module": "test_brand_new_unknown_breakage.py",
            "status": "fail", "returncode": 1, "tests": 1,
            "errors": 1, "failures": 0, "diagnostic": "synthetic",
        })
        with self.assertRaisesRegex(ScopeRefused, "inconsistent"):
            self.classify(report)

    def test_retired_module_source_changed_requires_explicit_re_review(self):
        edited = "test_accounting_bridge.py"
        original_read = Path.read_bytes

        def synthetic_edit(path):
            raw = original_read(path)
            if path.name == edited and path.parent == self.test_dir:
                return raw + b"\n# source modified after retirement review\n"
            return raw

        with patch.object(Path, "read_bytes", autospec=True,
                          side_effect=synthetic_edit):
            with self.assertRaisesRegex(ScopeRefused, "source changed"):
                self.classify()

    def test_unreviewed_exclusions_and_hidden_old_failure_are_rejected(self):
        modified = deepcopy(self.historical)
        modified["summary"]["modules_excluded"].append(
            "test_mtr_e2_recovery_security_20261110.py")
        with self.assertRaisesRegex(ScopeRefused, "unexpected hidden exclusions"):
            self.classify(modified)
        missing = deepcopy(self.historical)
        missing["modules"] = [r for r in missing["modules"]
                              if r["module"] != "test_accounting_bridge.py"]
        with self.assertRaisesRegex(ScopeRefused, "missing"):
            self.classify(missing)

    def test_falsified_counts_or_duplicate_module_cannot_create_false_pass(self):
        report = deepcopy(self.historical)
        report["summary"]["test_errors"] = 0
        with self.assertRaisesRegex(ScopeRefused, "inconsistent"):
            self.classify(report)
        report = deepcopy(self.historical)
        report["modules"][0]["status"] = "pass"
        with self.assertRaises(ScopeRefused):
            self.classify(report)
        report = deepcopy(self.historical)
        report["modules"][1]["module"] = report["modules"][0]["module"]
        with self.assertRaisesRegex(ScopeRefused, "duplicate"):
            self.classify(report)

    def test_run_scope_requires_exact_reviewed_set_digest_and_real_source_dir(self):
        result = self.classify()
        with patch("mtr_release_suite_scope.execute_module") as runner:
            for invalid in (None, "", "a" * 64, retired_set_digest()[:-1]):
                with self.subTest(invalid=invalid):
                    with self.assertRaisesRegex(ScopeRefused, "acknowledgment"):
                        run_current_scope(self.test_dir, result,
                                          reviewed_digest=invalid,
                                          known_only=True)
            with tempfile.TemporaryDirectory(prefix="mtr-scope-wrong-root-") as tmp:
                with self.assertRaisesRegex(ScopeRefused, "actual reviewed"):
                    run_current_scope(Path(tmp), result,
                                      reviewed_digest=retired_set_digest(),
                                      known_only=True)
        runner.assert_not_called()

    def test_current_module_inventory_cannot_hide_unlisted_or_packaged_tests(self):
        result = self.classify()
        current = current_modules(self.test_dir, result, known_only=False)
        names = {path.name for path in current}
        self.assertFalse(names & set(REVIEWED_RETIRED_SOURCES))
        self.assertNotIn(PACKAGED_EXE_TEST, names)
        self.assertFalse(names & set(REVIEWED_RELEASE_ONLY_SOURCES))
        self.assertIn("test_mtr_e2_recovery_security_20261110.py", names)
        self.assertIn("test_mtr_release_suite_scope.py", names)
        discovered = {path.name for path in self.test_dir.glob("test_*.py")}
        self.assertEqual(names | set(REVIEWED_RETIRED_SOURCES)
                         | set(REVIEWED_RELEASE_ONLY_SOURCES)
                         | ({PACKAGED_EXE_TEST} & discovered), discovered)
        targeted = current_modules(self.test_dir, result, known_only=True)
        self.assertEqual([path.name for path in targeted], sorted(KNOWN_CURRENT_FAILURES))

    def test_release_only_rc_installer_exclusion_requires_reviewed_bytes(self):
        result = self.classify()
        self.assertIn("test_release_portable_install.py", REVIEWED_RELEASE_ONLY_SOURCES)
        with patch("mtr_release_suite_scope.REVIEWED_RELEASE_ONLY_SOURCES", {
            "test_release_portable_install.py": "0" * 64
        }):
            with self.assertRaisesRegex(ScopeRefused, "release-only installer source changed"):
                current_modules(self.test_dir, result, known_only=False)

    def test_disposable_runner_reuses_existing_module_isolation_and_retains_failure(self):
        result = self.classify()
        captured = []

        def fake_execute(path, scratch, timeout, legacy_seed):
            captured.append((path.name, scratch, timeout, legacy_seed,
                             dict(os.environ)))
            return {
                "module": path.name, "status": "fail", "returncode": 1,
                "tests": 15, "errors": 1, "failures": 0,
                "diagnostic": "synthetic current regression failed",
            }

        snapshot = {
            "fingerprintSha256": "a" * 64, "fileCount": 2,
            "totalBytes": 42, "files": {"sample.py": "b" * 64},
        }
        with patch("mtr_release_suite_scope.execute_module",
                   side_effect=fake_execute), patch(
                       "mtr_release_suite_scope.capture_source_snapshot",
                       return_value=snapshot), redirect_stdout(io.StringIO()):
            outcome = run_current_scope(
                self.test_dir, result, reviewed_digest=retired_set_digest(),
                known_only=True, workers=1,
            )
        self.assertEqual(len(captured), 1)
        module_name, scratch, timeout, legacy_seed, environment = captured[0]
        self.assertEqual(module_name, "test_mtr_e2_recovery_security_20261110.py")
        self.assertEqual(timeout, 120)
        self.assertFalse(legacy_seed)
        self.assertIn("madar-e0-e7-current-scope-", str(scratch))
        self.assertNotEqual(environment.get("APPDATA"), os.environ.get("APPDATA"))
        self.assertNotEqual(environment.get("USERPROFILE"), os.environ.get("USERPROFILE"))
        self.assertEqual(outcome["failed"], 1)
        self.assertEqual(outcome["passed"], 0)
        self.assertFalse(outcome["historicalFullSuitePassed"])
        self.assertEqual(outcome["historicalFullSuiteErrors"], 118)
        self.assertEqual(outcome["historicalFullSuiteAssertions"], 9)
        self.assertIn("test_release_portable_install.py",
                      outcome["excludedReleaseOnlyModuleNames"])
        self.assertEqual(outcome["unknownTestModuleNamesSinceReport"], [])
        self.assertIn("TARGETED", outcome["scope"])
        self.assertEqual(outcome["sourceSnapshotSha256"], "a" * 64)
        self.assertEqual(outcome["sourceSnapshotFiles"], 2)
        self.assertEqual(outcome["sourceSnapshotBytes"], 42)
        self.assertTrue(outcome["sourceSnapshotMatchedPrePost"])

    def _synthetic_source(self, root):
        source = root / "src"
        tests = root / "tests"
        source.mkdir()
        tests.mkdir()
        (source / "engine.py").write_text("ANSWER = 42\n", encoding="utf-8")
        (tests / "test_one.py").write_text("def test_one(): return True\n",
                                           encoding="utf-8")
        return source / "engine.py", tests / "test_one.py"

    @staticmethod
    def _synthetic_classification():
        return {
            "unknownFailedModules": [],
            "historicalFullSuitePassed": False,
            "historicalFullSuite": {"test_errors": 118, "test_failures": 9},
            "retiredAccountingModuleNames": list(REVIEWED_RETIRED_SOURCES),
            "historicalExecutedModuleNames": ["test_one.py"],
        }

    def _run_synthetic_source_gate(self, root: Path, mutation, *,
                                   result_override=None, taraz_source=None):
        test_dir = root / "tests"
        test_path = test_dir / "test_one.py"
        calls = []

        def fake_execute(path, scratch, timeout, legacy_seed):
            calls.append(path.name)
            mutation()
            outcome = {
                "module": path.name, "status": "pass", "returncode": 0,
                "tests": 1, "errors": 0, "failures": 0, "diagnostic": "",
            }
            outcome.update(result_override or {})
            return outcome

        with patch("mtr_release_suite_scope.PROJECT", root), patch(
            "mtr_release_suite_scope.current_modules", return_value=[test_path]
        ), patch("mtr_release_suite_scope.execute_module",
                 side_effect=fake_execute), redirect_stdout(io.StringIO()):
            try:
                result = run_current_scope(
                    test_dir, self._synthetic_classification(),
                    reviewed_digest=retired_set_digest(),
                    known_only=False, workers=1,
                    taraz_source=taraz_source,
                )
            finally:
                self.assertEqual(calls, ["test_one.py"])
        return result

    def test_zero_test_missing_count_and_all_skipped_never_pass(self):
        for label, override in (
            ("zero", {"tests": 0, "skipped": 1}),
            ("missing", {"tests": None}),
            ("all-skipped", {"tests": 2, "skipped": 2}),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory(
                prefix="mtr-source-zero-test-"
            ) as temp:
                root = Path(temp)
                self._synthetic_source(root)
                with self.assertRaisesRegex(ScopeRefused, "zero-test, all-skipped"):
                    self._run_synthetic_source_gate(
                        root, lambda: None, result_override=override)

    def test_cross_source_test_is_blocked_without_explicit_detached_source(self):
        with tempfile.TemporaryDirectory(prefix="mtr-cross-source-required-") as temp:
            root = Path(temp)
            self._synthetic_source(root)
            test = root / "tests" / "test_mtr_e4_local_catalog_pilot.py"
            test.write_text("def test_only(): pass\n", encoding="utf-8")
            with patch("mtr_release_suite_scope.PROJECT", root), patch(
                "mtr_release_suite_scope.current_modules", return_value=[test]
            ), patch("mtr_release_suite_scope.execute_module") as runner, patch.dict(
                os.environ, {"MTR_TARAZ_SOURCE": "C:\\Unreviewed\\Taraz"}
            ):
                with self.assertRaisesRegex(ScopeRefused, "explicit detached Taraz"):
                    run_current_scope(root / "tests", self._synthetic_classification(),
                                      reviewed_digest=retired_set_digest())
            runner.assert_not_called()

    def test_explicit_taraz_source_is_pinned_checked_and_snapshot_attested(self):
        with tempfile.TemporaryDirectory(prefix="mtr-cross-source-pinned-") as temp:
            root = Path(temp)
            madar = root / "madar"
            madar.mkdir()
            self._synthetic_source(madar)
            source = root / "detached-taraz"
            source.mkdir()
            (source / ".git").write_text("synthetic worktree marker", encoding="utf-8")
            for name in ("taraz_mtr_peer_registry.py", "taraz_mtr_peer_http.py",
                         "taraz_mtr_catalog_read.py", "taraz_integration.py"):
                (source / name).write_text("# synthetic only\n", encoding="utf-8")
            env_seen = []

            def observe():
                env_seen.append(os.environ.get("MTR_TARAZ_SOURCE"))

            with patch("mtr_release_suite_scope.DETACHED_TARAZ_WORKTREE", source):
                self.assertEqual(validate_detached_taraz_source(source), source.resolve())
                with self.assertRaisesRegex(ScopeRefused, "reviewed detached"):
                    validate_detached_taraz_source(madar)
                with self.assertRaisesRegex(ScopeRefused, "absolute"):
                    validate_detached_taraz_source(Path("relative-taraz"))
                with patch.dict(os.environ, {"MTR_TARAZ_SOURCE": "unreviewed"}):
                    result = self._run_synthetic_source_gate(
                        madar, observe, taraz_source=source)
                self.assertEqual(env_seen, [str(source.resolve())])
                self.assertEqual(result["detachedTarazSourceFiles"], 4)
                self.assertTrue(result["detachedTarazSourceMatchedPrePost"])
                self.assertRegex(result["detachedTarazSourceSha256"],
                                 r"\A[0-9a-f]{64}\Z")

    def test_repo_wide_source_snapshot_includes_untracked_hidden_and_tests(self):
        with tempfile.TemporaryDirectory(prefix="mtr-source-snapshot-") as tmp:
            root = Path(tmp)
            self._synthetic_source(root)
            (root / ".hidden.py").write_text("DATA=5\n", encoding="utf-8")
            # Explicitly documented omissions are caches/dependencies only.
            for ignore in ("__pycache__", ".venv", "node_modules"):
                folder = root / ignore
                folder.mkdir()
                (folder / "not-source.py").write_text("ignored", encoding="utf-8")
            first = capture_source_snapshot(root)
            second = capture_source_snapshot(root)
            require_unchanged_source_snapshot(first, second)
            self.assertEqual(first["fileCount"], 3)
            self.assertEqual(set(first["files"]), {
                ".hidden.py", "src/engine.py", "tests/test_one.py",
            })
            self.assertEqual(first["fingerprintSha256"], second["fingerprintSha256"])
            self.assertRegex(first["fingerprintSha256"], r"\A[0-9a-f]{64}\Z")

    def test_sha_snapshot_blocks_same_size_edit_during_suite(self):
        with tempfile.TemporaryDirectory(prefix="mtr-source-edit-") as tmp:
            root = Path(tmp)
            source, _ = self._synthetic_source(root)
            with self.assertRaisesRegex(ScopeRefused, "modified=1"):
                self._run_synthetic_source_gate(
                    root, lambda: source.write_text("ANSWER = 43\n", encoding="utf-8"),
                )

    def test_sha_snapshot_blocks_added_python_source_during_suite(self):
        with tempfile.TemporaryDirectory(prefix="mtr-source-added-") as tmp:
            root = Path(tmp)
            self._synthetic_source(root)
            with self.assertRaisesRegex(ScopeRefused, "added=1"):
                self._run_synthetic_source_gate(
                    root, lambda: (root / "src" / "untracked.py").write_text(
                        "new = True\n", encoding="utf-8"),
                )

    def test_sha_snapshot_blocks_deleted_python_source_during_suite(self):
        with tempfile.TemporaryDirectory(prefix="mtr-source-deleted-") as tmp:
            root = Path(tmp)
            source, _ = self._synthetic_source(root)
            with self.assertRaisesRegex(ScopeRefused, "deleted=1"):
                self._run_synthetic_source_gate(root, source.unlink)

    def test_sha_snapshot_blocks_jsx_component_change_during_python_suite(self):
        with tempfile.TemporaryDirectory(prefix="mtr-source-jsx-") as tmp:
            root = Path(tmp)
            self._synthetic_source(root)
            component = root / "src" / "component.jsx"
            component.write_text("export default 1;\n", encoding="utf-8")
            with self.assertRaisesRegex(ScopeRefused, "modified=1"):
                self._run_synthetic_source_gate(
                    root, lambda: component.write_text(
                        "export default 2;\n", encoding="utf-8"),
                )

    def test_sha_snapshot_blocks_new_powershell_release_script_during_suite(self):
        with tempfile.TemporaryDirectory(prefix="mtr-source-powershell-") as tmp:
            root = Path(tmp)
            self._synthetic_source(root)
            scripts = root / "scripts"
            scripts.mkdir()
            with self.assertRaisesRegex(ScopeRefused, "added=1"):
                self._run_synthetic_source_gate(
                    root, lambda: (scripts / "unsafe-updater.ps1").write_text(
                        "Write-Output 'changed'\n", encoding="utf-8"),
                )

    def test_sha_snapshot_denies_unsafe_symlink_in_scanned_tree(self):
        with tempfile.TemporaryDirectory(prefix="mtr-source-link-") as tmp:
            root = Path(tmp)
            source, _ = self._synthetic_source(root)
            external = root / "external.txt"
            external.write_text("not part of source", encoding="utf-8")
            link = root / "src" / "linked.py"
            try:
                link.symlink_to(external)
            except (OSError, NotImplementedError):
                # Windows installations without symlink privilege: inject a
                # synthetic lstat result that is a symlink, not a skip/pass.
                actual = os.scandir

                class LinkEntry:
                    def __init__(self, entry):
                        self.wrapped = entry
                        self.name = entry.name
                        self.path = entry.path

                    def stat(self, *, follow_symlinks):
                        info = self.wrapped.stat(follow_symlinks=follow_symlinks)
                        if Path(self.path) != source:
                            return info
                        fields = list(info)
                        fields[0] = stat.S_IFLNK | 0o777
                        return os.stat_result(fields)

                def fake_scandir(path):
                    from contextlib import nullcontext
                    with actual(path) as entries:
                        return nullcontext([LinkEntry(entry) for entry in entries])

                with patch("mtr_release_suite_scope.os.scandir",
                           side_effect=fake_scandir):
                    with self.assertRaisesRegex(ScopeRefused, "symlink/reparse"):
                        capture_source_snapshot(root)
            else:
                with self.assertRaisesRegex(ScopeRefused, "symlink/reparse"):
                    capture_source_snapshot(root)
            self.assertTrue(source.is_file())

    def test_fresh_symlink_added_during_run_fails_without_success_receipt(self):
        with tempfile.TemporaryDirectory(prefix="mtr-source-link-run-") as tmp:
            root = Path(tmp)
            source, _ = self._synthetic_source(root)

            def synthetic_link():
                target = root / "src" / "newlink.py"
                target.symlink_to(source)

            try:
                # Probe permission only inside disposable fixture.
                probe = root / "probe.txt"
                probe.symlink_to(source)
                probe.unlink()
            except (OSError, NotImplementedError):
                self.skipTest("Windows symlink privilege unavailable; injected metadata test covers denial")
            with self.assertRaisesRegex(ScopeRefused, "symlink/reparse"):
                self._run_synthetic_source_gate(root, synthetic_link)

    def test_matching_synthetic_run_reports_snapshot_digest_and_counts(self):
        with tempfile.TemporaryDirectory(prefix="mtr-source-match-") as tmp:
            root = Path(tmp)
            self._synthetic_source(root)
            result = self._run_synthetic_source_gate(root, lambda: None)
            self.assertEqual(result["passed"], 1)
            self.assertTrue(result["sourceSnapshotMatchedPrePost"])
            self.assertEqual(result["sourceSnapshotFiles"], 2)
            self.assertRegex(result["sourceSnapshotSha256"],
                             r"\A[0-9a-f]{64}\Z")
            self.assertFalse(result["historicalFullSuitePassed"])
            self.assertEqual((result["historicalFullSuiteErrors"],
                              result["historicalFullSuiteAssertions"]), (118, 9))

    def test_new_test_added_between_selection_and_initial_snapshot_is_not_skipped(self):
        with tempfile.TemporaryDirectory(prefix="mtr-source-select-race-") as tmp:
            root = Path(tmp)
            self._synthetic_source(root)
            tests = root / "tests"
            snapshot_capture = capture_source_snapshot
            calls = []

            def capture_then_add(folder):
                frozen = snapshot_capture(folder)
                (tests / "test_new.py").write_text("def test_new(): pass\n",
                                                    encoding="utf-8")
                return frozen

            def discover(test_dir, _classification, *, known_only):
                self.assertFalse(known_only)
                return sorted(test_dir.glob("test_*.py"))

            with patch("mtr_release_suite_scope.PROJECT", root), patch(
                "mtr_release_suite_scope.capture_source_snapshot",
                side_effect=capture_then_add,
            ), patch("mtr_release_suite_scope.current_modules",
                     side_effect=discover), patch(
                         "mtr_release_suite_scope.execute_module",
                         side_effect=lambda *args: calls.append(args),
                     ):
                with self.assertRaisesRegex(ScopeRefused,
                                            "test inventory changed before"):
                    run_current_scope(
                        tests, self._synthetic_classification(),
                        reviewed_digest=retired_set_digest(), workers=1,
                    )
            self.assertEqual(calls, [])

    def test_cli_returns_blocked_not_pass_on_source_snapshot_mismatch(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch("mtr_release_suite_scope.run_current_scope",
                   side_effect=ScopeRefused(
                       "Python source snapshot changed during current-scope run"
                   )) as scoped_run, redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main([
                "--historical-report", str(HISTORICAL_REPORT),
                "--test-dir", str(self.test_dir),
                "--run-current", "--known-failures-only",
                "--approve-retired-sha256", retired_set_digest(),
            ])
        self.assertEqual(exit_code, 2)
        scoped_run.assert_called_once()
        self.assertIn("SCOPE_BLOCKED", stderr.getvalue())
        self.assertNotIn("CURRENT_SCOPE_QA", stdout.getvalue())
        self.assertIn('"test_errors": 118', stdout.getvalue())
        self.assertIn('"test_failures": 9', stdout.getvalue())

    def test_snapshot_rejects_relative_root_and_explicit_source_bounds(self):
        with self.assertRaisesRegex(ScopeRefused, "absolute"):
            capture_source_snapshot(Path("relative-project"))
        with tempfile.TemporaryDirectory(prefix="mtr-source-limit-") as tmp:
            root = Path(tmp)
            self._synthetic_source(root)
            with patch("mtr_release_suite_scope._SOURCE_MAX_FILES", 1):
                with self.assertRaisesRegex(ScopeRefused, "file inventory bound"):
                    capture_source_snapshot(root)
            with patch("mtr_release_suite_scope._SOURCE_MAX_SINGLE_BYTES", 2):
                with self.assertRaisesRegex(ScopeRefused, "safety bound"):
                    capture_source_snapshot(root)
            with patch("mtr_release_suite_scope._SOURCE_MAX_ENTRIES", 1):
                with self.assertRaisesRegex(ScopeRefused, "entry inventory bound"):
                    capture_source_snapshot(root)

    def test_cli_prints_retired_names_and_original_truth_returns_nonzero(self):
        printed, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(printed), redirect_stderr(errors), patch(
            "mtr_release_suite_scope.execute_module"
        ) as runner:
            exit_code = main([
                "--historical-report", str(HISTORICAL_REPORT),
                "--test-dir", str(self.test_dir),
            ])
        runner.assert_not_called()
        self.assertEqual(exit_code, 1)
        self.assertIn("test_accounting_bridge.py", printed.getvalue())
        self.assertIn('"test_errors": 118', printed.getvalue())
        self.assertIn('"test_failures": 9', printed.getvalue())
        self.assertIn('"historicalFullSuitePassed": false', printed.getvalue())

    def test_cli_refuses_unreviewed_failure_and_does_not_spawn_tests(self):
        report = deepcopy(self.historical)
        passing = next(r for r in report["modules"] if r["status"] == "pass")
        passing.update(status="fail", returncode=1, errors=1)
        report["summary"]["modules_passed"] -= 1
        report["summary"]["modules_failed"] += 1
        report["summary"]["test_errors"] += 1
        with tempfile.TemporaryDirectory(prefix="mtr-scope-cli-") as tmp:
            file = Path(tmp) / "synthetic_full_qa.json"
            file.write_text(json.dumps(report), encoding="utf-8")
            with patch("mtr_release_suite_scope.execute_module") as runner, (
                    redirect_stdout(io.StringIO())), redirect_stderr(io.StringIO()):
                exit_code = main([
                    "--historical-report", str(file),
                    "--run-current", "--known-failures-only",
                    "--approve-retired-sha256", retired_set_digest(),
                ])
        runner.assert_not_called()
        self.assertEqual(exit_code, 2)


if __name__ == "__main__":
    unittest.main()
