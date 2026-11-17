"""Create-only, disposable source snapshot QA for Madar Sileo/context help.

No installed processes, user profiles, network, finance services, external
builder, installer or production file mutations in these unit tests.
"""
from __future__ import annotations

from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "qa_madar_sileo_v126_20261110.py"
spec = importlib.util.spec_from_file_location("qa_madar_sileo_v126_20261110", SCRIPT)
qa = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(qa)


def write(path: Path, value: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value.encode("utf-8") if isinstance(value, str) else value)


def fake_source(root: Path):
    root.mkdir()
    pkg = {"name": "madar-desk", "version": "1.0.26",
           "dependencies": {"sileo": "0.1.6"}}
    lock = {"version": "1.0.26", "packages": {
        "": {"version": "1.0.26", "dependencies": {"sileo": "0.1.6"}},
        "node_modules/sileo": {"version": "0.1.6"}}}
    write(root / "package.json", json.dumps(pkg))
    write(root / "package-lock.json", json.dumps(lock))
    write(root / "vite.config.js", "export default {};")
    write(root / "index.html", '<div id="root"></div>')
    write(root / "native_app.py", "# synthetic source only\n")
    write(root / "madar_update.py", "# synthetic source only\n")
    write(root / "scripts" / "sync_font.py", "# synthetic only\n")
    write(root / "public" / "madar-icon.svg", "<svg></svg>")
    write(root / "assets" / "madar.ico", b"ICON")
    write(root / "src" / "App.jsx", """
import {MadarSileoFeedback} from './mtr_sileo_feedback.jsx';
import {MadarContextHelp} from './mtr_context_help.jsx';
function App(){return <>
<MadarSileoFeedback/>
<MadarContextHelp currentSection={helpCurrentSection} availableSections={helpAvailableSections}/>
</>};
""")
    write(root / "src" / "mtr_sileo_feedback.jsx",
          "import {Toaster} from 'sileo';export default ()=> <Toaster/>;")
    write(root / "src" / "mtr_context_help.jsx",
          "export const MadarContextHelp=()=> 'mtr-context-help__trigger';")
    write(root / "src" / "mtr_context_help_data.js",
          "export const MADAR_HELP_SECTIONS = []")
    write(root / "node_modules" / "sileo" / "package.json",
          json.dumps({"name": "sileo", "version": "0.1.6"}))
    write(root / "node_modules" / "vite" / "bin" / "vite.js", "console.log('qa');")
    return root


def write_compiled(snapshot: Path, output: Path, run: Path):
    # This synthetic builder is only a test double for output validation.
    output.mkdir()
    write(output / "index.html", '<div id="root"></div><script src="./assets/index-qa.js"></script>')
    write(output / "assets" / "index-qa.js",
          "data-sileo-viewport data-sileo-toast "
          "mtr-context-help__trigger راهنمای مدار tarazIntegrationQueue")
    write(output / "assets" / "index-qa.css",
          ".mtr-context-help{display:block}[data-sileo-viewport]{display:block}")
    return "synthetic builder; NOT a Vite execution"


class QaOnlySnapshotTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(
            prefix="mtr-sileo-qa-synthetic-", dir=r"D:\CoS-Test")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.source = fake_source(self.root / "fake-source")
        self.qa_root = self.root / "qa-only"
        self.install = self.root / "fake-localappdata"

    def run_qa(self, *, build=write_compiled, installed_audit=None):
        return qa.build_qa(
            source=self.source, qa_root=self.qa_root, build=build,
            installed_audit=installed_audit or (
                lambda: {"status": "SYNTHETIC_NOT_INSTALLED"}),
        )

    def test_source_scan_and_locked_sileo_preflight(self):
        self.assertEqual(qa.require_ready(self.source)["sileoRootMounts"], 1)
        sources = qa.inventory(self.source)
        deps = qa.inventory(self.source, dependencies=True)
        self.assertIn("src/App.jsx", sources)
        self.assertIn("package-lock.json", sources)
        self.assertIn("node_modules/sileo/package.json", deps)
        self.assertEqual(sources, qa.inventory(self.source))
        self.assertEqual(len(qa._encoded_sha(sources)), 64)

    def test_successful_create_only_snapshot_with_exact_artifact_hashes(self):
        first = self.run_qa()
        self.assertEqual(first["status"], "QA_VITE_SOURCE_SNAPSHOT_VERIFIED")
        self.assertTrue(all(first["compiled"]["checks"].values()))
        self.assertEqual(first["installedApplicationModified"], False)
        self.assertEqual(first["windowsExecutable"], "NOT_BUILT")
        folder = Path(first["outputRoot"])
        self.assertTrue((folder / "qa-report.json").is_file())
        copied_app = folder / "source-snapshot" / "src" / "App.jsx"
        self.assertEqual(copied_app.read_bytes(),
                         (self.source / "src" / "App.jsx").read_bytes())
        manifest = json.loads((folder / "source-manifest.json").read_text())
        self.assertEqual(manifest["sourceSha256"], first["sourceSha256"])
        self.assertEqual(manifest["dependencySha256"], first["dependencySha256"])
        self.assertEqual(manifest["sourceFiles"]["src/App.jsx"], qa._digest(copied_app))
        first_report_sha = qa._digest(folder / "qa-report.json")
        second = self.run_qa()
        self.assertEqual(second["status"], "QA_VITE_SOURCE_SNAPSHOT_VERIFIED")
        self.assertNotEqual(second["outputRoot"], first["outputRoot"])
        self.assertEqual(qa._digest(folder / "qa-report.json"), first_report_sha)

    def test_unwired_help_blocks_before_creating_output(self):
        app = self.source / "src" / "App.jsx"
        app.write_text(app.read_text().replace(
            "<MadarContextHelp currentSection={helpCurrentSection} availableSections={helpAvailableSections}/>",
            ""), encoding="utf-8")
        with self.assertRaisesRegex(qa.QaBlocked, "wired"):
            self.run_qa()
        self.assertFalse(self.qa_root.exists())

    def test_mismatched_package_lock_or_node_modules_blocks(self):
        lock = self.source / "package-lock.json"
        data = json.loads(lock.read_text())
        data["packages"]["node_modules/sileo"]["version"] = "0.1.5"
        write(lock, json.dumps(data))
        with self.assertRaisesRegex(qa.QaBlocked, "Sileo"):
            self.run_qa()
        self.assertFalse(self.qa_root.exists())

    def test_existing_unregistered_symlink_source_is_refused(self):
        link = self.source / "src" / "linked-source.js"
        try:
            link.symlink_to(self.source / "src" / "App.jsx")
        except (OSError, NotImplementedError):
            self.skipTest("host does not allow synthetic symlink creation")
        with self.assertRaisesRegex(qa.QaBlocked, "linked"):
            self.run_qa()
        self.assertFalse(self.qa_root.exists())

    def test_source_edit_during_compilation_fails_closed(self):
        def source_modified(snapshot, output, run):
            output_log = write_compiled(snapshot, output, run)
            app = self.source / "src" / "App.jsx"
            app.write_text(app.read_text() + "\n// mid-build edit", encoding="utf-8")
            return output_log

        result = self.run_qa(build=source_modified)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("SOURCE_CHANGED_DURING_BUILD", result["reason"])
        self.assertTrue(Path(result["outputRoot"], "qa-report.json").exists())

    def test_new_source_file_during_compilation_fails_closed(self):
        def source_added(snapshot, output, run):
            write_compiled(snapshot, output, run)
            write(self.source / "src" / "new-file.js", "export const x=1;")
            return "synthetic"
        result = self.run_qa(build=source_added)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("SOURCE_CHANGED_DURING_BUILD", result["reason"])

    def test_dependency_change_during_compilation_fails_closed(self):
        def dep_modified(snapshot, output, run):
            write_compiled(snapshot, output, run)
            write(self.source / "node_modules" / "sileo" / "package.json",
                  '{"name":"sileo","version":"0.1.6","mutated":true}')
            return "synthetic"
        result = self.run_qa(build=dep_modified)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("SOURCE_CHANGED_DURING_BUILD", result["reason"])

    def test_missing_compiled_help_or_sileo_never_passes(self):
        def missing_help(snapshot, output, run):
            write_compiled(snapshot, output, run)
            write(output / "assets" / "index-qa.js",
                  "data-sileo-viewport data-sileo-toast tarazIntegrationQueue")
            return "synthetic"
        result = self.run_qa(build=missing_help)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("compiled bundle missing", result["reason"])

    def test_exact_default_installed_v126_readonly_and_no_downgrade(self):
        install_root = self.install / "Programs" / "MadarDesk"
        pointer = install_root / "current-version.txt"
        exe = install_root / "versions" / "1.0.26" / "Madar-Desk.exe"
        write(pointer, "1.0.26\n")
        write(exe, b"MZ" + b"synthetic-only-pe-file")
        original_pointer = sha256(pointer.read_bytes()).hexdigest()
        original_exe = qa._digest(exe)
        result = qa.audit_installed(localappdata=self.install)
        self.assertEqual(result["status"], "EXACT_V126_PE_FOUND")
        self.assertEqual(result["installedVersion"], "1.0.26")
        self.assertEqual(result["versionComparison"], "SAME_VERSION_NO_OVERWRITE")
        self.assertEqual(result["exeSha256"], original_exe)
        self.assertEqual(sha256(pointer.read_bytes()).hexdigest(), original_pointer)
        self.assertEqual(qa._digest(exe), original_exe)
        write(pointer, "1.0.27\n")
        newer = qa.audit_installed(localappdata=self.install)
        self.assertEqual(newer["versionComparison"], "INSTALLED_NEWER_NO_DOWNGRADE")
        self.assertEqual(newer["status"], "EXACT_V126_PE_FOUND")


if __name__ == "__main__":
    unittest.main()
