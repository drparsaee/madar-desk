"""Disposable QA-only tests; NEVER execute the installed app or Inno setup."""
from __future__ import annotations

from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile


SCRIPT = Path(__file__).resolve().parents[1] / (
    "scripts/qa_madar_v127_update_package_20261110.py")
spec = importlib.util.spec_from_file_location("madar_v127_package_gate", SCRIPT)
qa = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(qa)


class ReadonlyQAUpdateTests(unittest.TestCase):
    def setUp(self):
        disposable = tempfile.TemporaryDirectory(
            prefix="madar-update-v127-synthetic-", dir=r"D:\CoS-Test")
        self.addCleanup(disposable.cleanup)
        self.root = Path(disposable.name)

    def test_strict_monotonic_candidate_not_a_renamed_old_exe(self):
        self.assertEqual(tuple(map(int, qa.TARGET.split("."))), (1, 0, 27))
        self.assertLess(tuple(map(int, qa.INSTALLED.split("."))),
                        tuple(map(int, qa.TARGET.split("."))))
        self.assertIn("1.0.27", qa.PAYLOAD_NAME)
        self.assertIn("QA-ONLY", qa.PAYLOAD_NAME)
        self.assertIn("QA-ONLY", qa.SETUP_NAME)
        self.assertNotEqual(qa.PRIOR_EXE_SHA, qa.CURRENT_INSTALLED_EXE_SHA)

    def test_exact_one_private_updater_version_overlay_no_mislabel(self):
        old = b'REPOSITORY="x"\nCURRENT_VERSION = "1.0.26"\nAPI="y"\n'
        newer = qa.overlay_version(old)
        self.assertIn(b'CURRENT_VERSION = "1.0.27"', newer)
        self.assertNotIn(b'CURRENT_VERSION = "1.0.26"', newer)
        self.assertIn(b'REPOSITORY="x"', newer)
        with self.assertRaises(qa.QaBlock):
            qa.overlay_version(newer)
        with self.assertRaises(qa.QaBlock):
            qa.overlay_version(old + old)

    def test_staged_package_lock_root_and_script_versions_equal(self):
        package = {"version": "1.0.26", "dependencies": {"sileo": "0.1.6"}}
        lock = {"version": "1.0.26", "packages": {
            "": {"version": "1.0.26", "dependencies": {"sileo": "0.1.6"}}}}
        result = json.loads(qa.set_pkg_version(json.dumps(package).encode()))
        other = json.loads(qa.set_pkg_version(json.dumps(lock).encode()))
        self.assertEqual(result["version"], "1.0.27")
        self.assertEqual(other["version"], "1.0.27")
        self.assertEqual(other["packages"][""]["version"], "1.0.27")
        self.assertEqual(result["dependencies"]["sileo"], "0.1.6")
        with self.assertRaises(qa.QaBlock):
            qa.set_pkg_version(b'{"version":"1.0.27"}')
        lock["packages"][""]["version"] = "1.0.25"
        with self.assertRaises(qa.QaBlock):
            qa.set_pkg_version(json.dumps(lock).encode())

    def test_isolated_qa_setup_flags_never_build_production_installer(self):
        root = qa.OUT / "stage" / "builder"
        synthetic = qa.OUT / ".qa-inno-v127-20261110"
        cmd = qa.qa_inno_command(root, "a" * 64, synthetic)
        self.assertIn("/DQA", cmd)
        self.assertIn("/DCOMPACT", cmd)
        self.assertIn("/DMadarVersion=1.0.27", cmd)
        self.assertIn("/DEXE_SHA256=" + "a" * 64, cmd)
        self.assertIn("/DQA_ROOT=" + str(synthetic), cmd)
        self.assertNotIn("/DPROD", cmd)
        self.assertEqual(cmd[-1], str(root / "scripts" / "madar-update.iss"))
        with self.assertRaises(qa.QaBlock):
            qa.qa_inno_command(root, "bad", synthetic)
        with self.assertRaises(qa.QaBlock):
            qa.qa_inno_command(root, "a" * 64, qa.OUT / "regular")
        with self.assertRaises(qa.QaBlock):
            qa.qa_inno_command(root, "a" * 64,
                               Path(r"C:\Users\real\AppData\Local\Programs\MadarDesk"))

    def test_snapshot_provenance_actual_embedded_old_version(self):
        inp = qa.pinned_inputs()
        self.assertEqual(inp["installedBefore"]["version"], "1.0.26")
        self.assertEqual(inp["priorExeSha256"], qa.PRIOR_EXE_SHA)
        self.assertEqual(inp["sourceManifestSha256"], qa.VITE_MANIFEST_SHA)
        self.assertEqual(inp["viteJsSha256"], qa.VITE_JS_SHA)
        self.assertEqual(
            qa.file_sha(inp["priorExe"]), qa.PRIOR_EXE_SHA)
        self.assertFalse(inp["priorExe"].is_relative_to(qa.OUT))

    def test_versioned_private_python_layer_never_reads_live_native(self):
        inp = qa.pinned_inputs()
        output = self.root / "python-qa"
        records = qa.previous_python_layer(inp, output)
        self.assertIn("madar_update.py", records)
        self.assertIn("native_app.py", records)
        self.assertEqual(records["native_app.py"],
                         inp["pythonManifest"]["pinnedCorePython"]["native_app.py"])
        self.assertNotEqual(records["madar_update.py"],
                            inp["pythonManifest"]["pinnedCorePython"]["madar_update.py"])
        self.assertIn('CURRENT_VERSION = "1.0.27"',
                      (output / "madar_update.py").read_text(encoding="utf-8"))
        self.assertEqual(len(records), 100)
        with self.assertRaises(FileExistsError):
            qa.previous_python_layer(inp, output)

    def test_zip_fallback_correctly_labels_earlier_real_binary(self):
        baseline = self.root / "baseline.exe"
        baseline.write_bytes(b"MZ" + b"example synthetic payload")
        original = qa.PRIOR_EXE_SHA
        with patch.object(qa, "PRIOR_EXE_SHA", qa.file_sha(baseline)):
            result = qa.fallback_zip(
                self.root, {"priorExe": baseline}, "synthetic compiler unavailable")
        path = self.root / qa.FALLBACK_NAME
        self.assertEqual(qa.file_sha(path), result["sha256"])
        with ZipFile(path) as zipfile:
            report = json.loads(zipfile.read("QA-ONLY-NO-SETUP.json"))
            self.assertEqual(report["actualPayloadRuntimeVersion"], "1.0.26")
            self.assertEqual(report["targetProposedVersion"], "1.0.27")
            self.assertEqual(report["status"],
                             "NO_EXECUTABLE_SETUP_ZIP_PROPOSAL_QA_ONLY")
            self.assertEqual(qa.data_sha(zipfile.read(qa.PRIOR_NAME)),
                             qa.file_sha(baseline))
        self.assertFalse((self.root / qa.SETUP_NAME).exists())
        self.assertRegex(original, r"^[0-9a-f]{64}$")

    def test_no_source_symlink_and_no_output_overwrite(self):
        original = self.root / "original.txt"
        original.write_text("original", encoding="utf-8")
        destination = self.root / "immutable-copy.txt"
        sha = qa.file_sha(original)
        qa.copy_verified(original, destination, sha)
        with self.assertRaises(FileExistsError):
            qa.copy_verified(original, destination, sha)
        original.write_text("changed", encoding="utf-8")
        with self.assertRaises(qa.QaBlock):
            qa.copy_verified(original, self.root / "other", sha)
        link = self.root / "link.txt"
        try:
            link.symlink_to(original)
        except OSError:
            return
        with self.assertRaises(qa.QaBlock):
            qa.safe(link)

    def test_prior_builder_safety_controls_present_without_executing(self):
        scripts = qa.original_builder_scripts_check()
        self.assertEqual(set(scripts), set(qa.REQUIRED))
        with tempfile.TemporaryDirectory(dir=str(self.root)) as d:
            target = Path(d)
            copied = qa.original_builder_scripts(target)
            self.assertEqual(copied, scripts)
        self.assertNotIn("Madar-Desk-1.0.27-Setup.exe", scripts)

    def test_runtime_setup_is_never_called_in_test_or_direct_script(self):
        code = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('"installerExecuted": False', code)
        self.assertIn('"installedApplicationModified": False', code)
        self.assertIn('"officialFinanceAcceptance": False', code)
        self.assertNotIn("Start-Process", code)
        self.assertNotIn("--noconfirm", code)
        self.assertNotIn("--clean", code)

    def test_original_compiled_frontend_version_is_v126_and_must_be_rebuilt(self):
        prior = qa.VITE / "vite-compiled" / "assets" / "main-Cd8KyHQW.js"
        text = prior.read_text(encoding="utf-8")
        self.assertEqual(text.count('"1.0.26"'), 1)
        self.assertIn("data-sileo-viewport", text)
        self.assertIn("mtr-context-help__trigger", text)
        new_source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("def compile_v127_ui(", new_source)
        self.assertIn('text.count("1.0.27") != 1', new_source)
        self.assertIn('"1.0.26" in text', new_source)
        self.assertIn("--rebuild-with-vite", new_source)

    def test_revised_build_is_create_only_without_replacing_old_candidate(self):
        code = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('revised = OUT / ("revised-source-v127-"', code)
        self.assertIn('revised.mkdir(exist_ok=False)', code)
        self.assertIn('"EARLIER_QA_CANDIDATE_SUPERSEDED.txt"', code)
        self.assertIn('"qaOnlyInstallRoot"', code)
        self.assertNotIn('Remove-Item', code)

    def test_hardened_inno_qa_dir_escape_guard_is_before_backup_and_file_copy(self):
        original = qa.SOURCE / "scripts" / "madar-update.iss"
        with tempfile.TemporaryDirectory(dir=str(self.root)) as d:
            stage = Path(d) / "madar-update.iss"
            stage.write_bytes(original.read_bytes())
            old_hash = qa.file_sha(original)
            hardened = qa.harden_qa_inno_stage(stage)
            new = hardened.read_text(encoding="utf-8")
            self.assertEqual(qa.file_sha(original), old_hash)
            self.assertIn("GetFileAttributesW@kernel32.dll", new)
            self.assertIn("QaPathHasJunctionOrLink", new)
            self.assertIn("CompareText(Expected, Actual) = 0", new)
            self.assertIn("ExpandFileName(ExpandConstant('{app}'))", new)
            self.assertEqual(new.count("QaExactInstallDestination()"), 3)
            prepare = new.index("function PrepareToInstall")
            check = new.index("if not QaExactInstallDestination()", prepare)
            backup = new.index("RunHiddenPowerShell('Madar-Upgrade-Preflight.ps1'", prepare)
            self.assertLess(check, backup)
            post = new.index("procedure CurStepChanged")
            self.assertIn("if not QaExactInstallDestination()", new[post:])
            self.assertEqual(qa.file_sha(stage), qa.file_sha(original))
            with self.assertRaises(FileExistsError):
                qa.harden_qa_inno_stage(stage)

    def test_actual_final_hardened_qa_setup_hash_and_isolated_version_readback(self):
        root = qa.OUT / "hardened-qa-v127-5ddf1f3e715f"
        report = json.loads((root / "qa-update-package-manifest.json").read_text(
            encoding="utf-8"))
        self.assertEqual(report["status"],
                         "QA_V127_INNO_DIR_HARDENED_SETUP_BUILT_NOT_INSTALLED")
        self.assertEqual(report["version"], "1.0.27")
        setup = Path(report["setupPath"])
        self.assertEqual(setup.name, qa.HARDENED_SETUP_NAME)
        self.assertEqual(report["setup"]["signatureStatus"], "NotSigned")
        self.assertEqual(report["setup"]["peVersion"], "1.0.27.0")
        self.assertEqual(report["setup"]["sha256"], qa.file_sha(setup))
        self.assertTrue(report["qaOnlyDefaultInstallRoot"].startswith(str(root)))
        self.assertFalse(report["installerExecuted"])
        self.assertFalse(report["installedModified"])
        self.assertEqual(report["installedVersionBefore"]["version"], "1.0.26")
        self.assertEqual(report["installedVersionBefore"]["sha256"],
                         qa._installed_readback()["sha256"])
        guarded = root / "builder/scripts/madar-update-QA-DIR-HARDENED.iss"
        self.assertEqual(report["hardenedInnoSha256"], qa.file_sha(guarded))
        self.assertIn("if not QaExactInstallDestination()",
                      guarded.read_text(encoding="utf-8"))
        self.assertTrue((qa.OUT / "UNSAFE_EARLIER_QA_SETUPS_DO_NOT_RUN.txt").is_file())


if __name__ == "__main__":
    unittest.main()
