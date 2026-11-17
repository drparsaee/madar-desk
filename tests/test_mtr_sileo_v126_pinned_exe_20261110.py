"""Negative, source-provenance and embedded-asset tests. No installer/app runs."""
from __future__ import annotations

from contextlib import ExitStack
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / (
    "scripts/qa_madar_sileo_v126_pinned_exe_20261110.py")
spec = importlib.util.spec_from_file_location(
    "mtr_qa_pinned_exe", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class QaPinnedExeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest, cls.report = module.pinned_manifest()

    def test_exact_real_snapshot_and_vite_feature_provenance(self):
        self.assertEqual(len(self.manifest["sourceFiles"]), 209)
        self.assertEqual(len(self.manifest["dependencyFiles"]), 7131)
        self.assertEqual(self.report["status"],
                         "QA_VITE_SOURCE_SNAPSHOT_VERIFIED")
        self.assertTrue(all(self.report["compiled"]["checks"].values()))
        self.assertEqual(
            self.report["compiled"]["assets"][module.VITE_MAIN]["sha256"],
            module.VITE_MAIN_SHA256)
        self.assertEqual(
            module.sha256_file(module.PINNED_RUN / "source-manifest.json"),
            module.MANIFEST_SHA256)

    def test_read_only_still_installed_same_version_no_upgrade(self):
        observed = module.installed_readonly_audit()
        self.assertEqual(observed.get("status"), "EXACT_V126_PE_FOUND")
        self.assertEqual(observed.get("versionComparison"),
                         "SAME_VERSION_NO_OVERWRITE")
        self.assertEqual(observed.get("installedVersion"), "1.0.26")
        self.assertEqual(observed.get("readOnly"), True)

    def test_command_create_only_exe_never_uses_installer_or_old_release_path(self):
        with tempfile.TemporaryDirectory(dir=r"D:\CoS-Test") as tmp:
            root = Path(tmp)
            cmd = module.pyinstaller_command(
                root, root / "python-input", module.PINNED_RUN / "vite-compiled")
            self.assertIn("--onefile", cmd)
            self.assertIn("--windowed", cmd)
            self.assertIn("--noupx", cmd)
            for forbidden in ("--noconfirm", "--clean", "--sign",
                              "scripts/build_p0_release_candidate.py",
                              "Madar-Setup.exe"):
                self.assertNotIn(forbidden, cmd)
            self.assertEqual(cmd[-1], str(root / "python-input" / "native_app.py"))
            self.assertEqual(cmd[cmd.index("--distpath") + 1],
                             str(root / "exe-dist"))
            self.assertEqual(cmd[cmd.index("--add-data") + 1],
                             str(module.PINNED_RUN / "vite-compiled") + ";dist")
            self.assertIn("QA-ONLY", module.EXE_NAME)
            self.assertNotEqual(
                module.EXE_NAME.lower(), "Madar-Desk.exe".lower())

    def test_private_isolated_build_environment_has_no_real_profile_values(self):
        with tempfile.TemporaryDirectory(dir=r"D:\CoS-Test") as tmp:
            root = Path(tmp)
            with patch.dict("os.environ", {
                    "APPDATA": r"C:\Users\real\AppData\Roaming",
                    "LOCALAPPDATA": r"C:\Users\real\AppData\Local",
                    "USERPROFILE": r"C:\Users\real",
                    "SECRET_KEY": "DO_NOT_COPY"}, clear=False):
                env = module.isolated_environment(root)
            for name in ("APPDATA", "LOCALAPPDATA", "HOME", "USERPROFILE",
                         "PYINSTALLER_CONFIG_DIR", "PYTHONPYCACHEPREFIX",
                         "TEMP", "TMP"):
                self.assertTrue(Path(env[name]).is_relative_to(root), name)
            self.assertNotIn("SECRET_KEY", env)
            self.assertEqual(env["PYTHONDONTWRITEBYTECODE"], "1")
            self.assertEqual(env["PYTHONNOUSERSITE"], "1")

    def test_supplementary_sources_hash_and_no_unpinned_native_entrypoint(self):
        extra = module.supplementary_python_files()
        self.assertGreaterEqual(len(extra), 11)
        self.assertNotIn("native_app.py", extra)
        self.assertNotIn("madar_update.py", extra)
        self.assertRegex(module.canonical_sha(extra), r"^[0-9a-f]{64}$")

    def test_python_stage_uses_exact_pinned_entrypoint_bytes(self):
        with tempfile.TemporaryDirectory(dir=r"D:\CoS-Test") as tmp:
            root = Path(tmp)
            extra = root / "source"
            extra.mkdir()
            (extra / "testmodule.py").write_text("x = 1\n", encoding="utf-8")
            pinned = root / "snapshot"
            pinned.mkdir()
            for name in ("native_app.py", "madar_update.py"):
                (pinned / name).write_text("# pinned " + name, encoding="utf-8")
            run = root / "run"
            run.mkdir()
            with patch.object(module, "ROOT", extra):
                copy = module.copy_python_layer(
                    run, {"testmodule.py": module.sha256_file(
                        extra / "testmodule.py")}, pinned)
            self.assertEqual(
                (copy / "native_app.py").read_bytes(),
                (pinned / "native_app.py").read_bytes())
            self.assertTrue((copy / "testmodule.py").is_file())
            with patch.object(module, "ROOT", extra):
                with self.assertRaises(FileExistsError):
                    module.copy_python_layer(
                        run, {"testmodule.py": module.sha256_file(
                            extra / "testmodule.py")}, pinned)

    def _fake_archive(self, file_map: dict[str, bytes]):
        class FakeArchive:
            def __init__(self, _):
                self.toc = {name: (0, 0, 0, 0, "x") for name in file_map}

            def extract(self, name):
                return file_map[name]
        return FakeArchive

    def _fake_exe(self, tmp: Path):
        exe = tmp / module.EXE_NAME
        exe.write_bytes(b"MZ" + b"\0" * 1_000_000)
        return exe

    def _fake_compiled(self, tmp: Path):
        compiled = tmp / "compiled"
        compiled.mkdir()
        js = ("data-sileo-viewport data-sileo-toast "
              "mtr-context-help__trigger راهنمای مدار").encode("utf-8")
        css = b".mtr-context-help {} [data-sileo-viewport] {}"
        (compiled / "assets").mkdir()
        (compiled / "assets" / "main.js").write_bytes(js)
        (compiled / "assets" / "main.css").write_bytes(css)
        attrs = {name: {"bytes": len(contents),
                        "sha256": sha256(contents).hexdigest()}
                 for name, contents in (("assets/main.js", js),
                                        ("assets/main.css", css))}
        report = {"compiled": {"assets": attrs}}
        archive = {"dist/" + name: (compiled / name).read_bytes()
                   for name in attrs}
        return compiled, report, archive

    def test_exe_archive_proves_exact_embedded_qa_frontend_hashes(self):
        with tempfile.TemporaryDirectory(dir=r"D:\CoS-Test") as tmp:
            root = Path(tmp)
            exe = self._fake_exe(root)
            compiled, report, archive = self._fake_compiled(root)
            with patch.object(module, "CArchiveReader",
                              self._fake_archive(archive)), patch.object(
                                  module, "VITE_MAIN", "assets/main.js"):
                result = module.verify_embedded_frontend(exe, report, compiled)
            self.assertTrue(result["embeddedSileoViewport"])
            self.assertTrue(result["embeddedHelpTrigger"])
            self.assertEqual(result["exeSha256"], module.sha256_file(exe))
            self.assertEqual(len(result["embeddedAssetsVerified"]), 2)

    def test_missing_embedded_help_and_modified_asset_are_blocked(self):
        with tempfile.TemporaryDirectory(dir=r"D:\CoS-Test") as tmp:
            root = Path(tmp)
            exe = self._fake_exe(root)
            compiled, report, archive = self._fake_compiled(root)
            with patch.object(module, "CArchiveReader",
                              self._fake_archive({})), patch.object(
                                  module, "VITE_MAIN", "assets/main.js"):
                with self.assertRaisesRegex(module.QaExeBlocked, "absent"):
                    module.verify_embedded_frontend(exe, report, compiled)
            archive["dist/assets/main.js"] = b"tampered"
            with patch.object(module, "CArchiveReader",
                              self._fake_archive(archive)), patch.object(
                                  module, "VITE_MAIN", "assets/main.js"):
                with self.assertRaisesRegex(module.QaExeBlocked, "differs"):
                    module.verify_embedded_frontend(exe, report, compiled)

    def test_installer_release_finance_proof_never_claimed_by_builder(self):
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('"installerBuilt": False', script)
        self.assertIn('"signed": False', script)
        self.assertIn('"deployed": False', script)
        self.assertIn('"officialFinanceReceiptVerified": False', script)
        self.assertIn('pinned_manifest()  # Full source/dependency', script)
        self.assertNotIn("subprocess.Popen(", script)
        self.assertNotIn("install.exe", script)


if __name__ == "__main__":
    unittest.main()
