"""Synthetic version and QA-provenance adversarial tests; no real installs."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "mtr_version_parity", ROOT / "scripts" / "qa_mtr_release_version_parity_20261110.py"
)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write(root: Path, rel: str, value) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, bytes):
        path.write_bytes(value)
    elif isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return path


class Archive:
    """Synthetic archive interface, not a packaged EXE verification claim."""

    data = {}

    def __init__(self, _):
        self.toc = {key: key for key in self.data}

    def extract(self, key):
        return self.data[key]


class VersionParityTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mtr-version-parity-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "source"
        self.root.mkdir()
        self.bundle = Path(self.temp.name) / "bundle"
        self.bundle.mkdir()
        self.version = "1.0.27"
        self._source()
        self._bundle()

    def _source(self):
        version = self.version
        package = {"name": "madar-desk", "version": version,
                   "dependencies": {"a": "1"}, "devDependencies": {"b": "2"},
                   "scripts": {"dist:rc": "python -B scripts/build_integrated_v127.py --webview2 "
                               "release/.madar-inno-prereq/MicrosoftEdgeWebView2RuntimeInstallerX64.exe"}}
        lock = {"name": "madar-desk", "version": version,
                "packages": {"": {"name": "madar-desk", "version": version,
                                   "dependencies": {"a": "1"}, "devDependencies": {"b": "2"}}}}
        write(self.root, "package.json", package)
        write(self.root, "package-lock.json", lock)
        write(self.root, "madar_update.py", f'CURRENT_VERSION = "{version}"\n')
        write(self.root, "scripts/build_integrated_v127.py",
              f'builder.VERSION = "{version}"\n'
              f'builder.PROGRAM = "Madar-Desk-{version}-Cumulative.exe"\n'
              f'builder.QA = "Madar-Desk-{version}-Setup-QA.exe"\n'
              f'builder.PROD = "Madar-Desk-{version}-Setup.exe"\n'
              f'MANIFEST = "Madar-Desk-{version}-Setup.release.json"\n')
        write(self.root, "scripts/build_p0_release_candidate.py",
              'args = ["/DMadarVersion=" + VERSION, "/DExeFile=" + PROGRAM.name]\n')
        write(self.root, "scripts/madar-update.iss",
              '#ifndef MadarVersion\n#define MadarVersion "1.0.2"\n#endif\n'
              'AppVersion={#MadarVersion}\nVersionInfoVersion={#MadarVersion}.0\n')
        for rel in mod.BASE_FILES:
            if not (self.root / rel).is_file():
                write(self.root, rel, f"synthetic {rel}\n")

    def _bundle(self):
        source = mod.inspect_source(self.root)
        version = self.version
        write(self.bundle, "source/package.json", {"version": version})
        write(self.bundle, "source/package-lock.json", {
            "version": version, "packages": {"": {"version": version}}})
        write(self.bundle, "source/madar_update.py", f'CURRENT_VERSION = "{version}"\n')
        asset = b"synthetic-vite-asset"
        write(self.bundle, "vite-dist/index.html", asset)
        assets = {"index.html": {"sha256": sha(asset), "bytes": len(asset)}}
        write(self.bundle, "vite-assets-sha256.json", assets)
        files = source["files"]
        snapshot_hash = sha("".join(f"{rel}\0{files[rel]['sha256']}\n"
                                     for rel in sorted(files)).encode("utf-8"))
        self.snapshot_pin = snapshot_hash
        write(self.bundle, "source-input-sha256.json", {
            "files": files, "fileCount": len(files),
            "sourceSnapshotTreeSha256": snapshot_hash})
        proof = {"purpose": "NON_RELEASE_QA", "appVersion": version,
                 "notFunctionalTestOrReleaseApproval": True,
                 "sourceSnapshotTreeSha256": snapshot_hash,
                 "sourceFileCount": len(files),
                 "viteAssetsSha256": mod._file_hash(self.bundle / "vite-assets-sha256.json")[0]}
        write(self.bundle, "qa-provenance.json", proof)
        self.provenance_pin = mod._file_hash(self.bundle / "qa-provenance.json")[0]
        self.exe = write(self.bundle, "exe-dist/qa-binary.exe", b"MZsynthetic-qa-only-bytes")
        self.qa_pin = mod._file_hash(self.exe)[0]
        write(self.bundle, "qa-build-result.json", {
            "schemaVersion": 1, "status": "QA_BUILT_NON_RELEASE",
            "purpose": "QA_ONLY_NON_RELEASE", "appVersion": version,
            "sourceSnapshotTreeSha256": snapshot_hash, "sourceFileCount": len(files),
            "application": {"filename": self.exe.name, "sha256": self.qa_pin,
                            "bytes": self.exe.stat().st_size, "releaseReady": False}})
        Archive.data = {"qa_proof/qa-provenance.json":
                        (self.bundle / "qa-provenance.json").read_bytes(),
                        "dist/index.html": asset}

    def _audit(self, **overrides):
        args = {"observed_installed": "1.0.26",
                "expected_source_sha256": mod.inspect_source(self.root)["sourceFingerprintSha256"],
                "bundle": self.bundle, "qa_artifact": self.exe,
                "expected_qa_sha256": self.qa_pin,
                "expected_qa_provenance_sha256": self.provenance_pin,
                "expected_snapshot_sha256": self.snapshot_pin,
                "archive_reader": Archive}
        args.update(overrides)
        return mod.audit(self.root, **args)

    def test_valid_synthetic_provenance_only_not_release(self):
        result = self._audit()
        self.assertEqual(result["decision"], "VERSION_PARITY_ONLY", result["checks"])
        self.assertFalse(result["mayInstall"])
        self.assertFalse(result["mayDeploy"])
        self.assertEqual(result["context"]["candidateVersion"], "1.0.27")
        self.assertTrue(result["checks"]["qa_candidate"]["embeddedProvenanceChecked"])

    def test_no_downgrade_including_equal_and_invalid(self):
        for installed in ("1.0.20", "1.0.27", "1.0.28", "1.1.0",
                          "1.0.26-beta", "01.0.26"):
            with self.subTest(installed=installed):
                result = self._audit(observed_installed=installed)
                self.assertEqual(result["decision"], "BLOCKED")
                self.assertIn("no_downgrade" if installed in
                              ("1.0.27", "1.0.28", "1.1.0")
                              else "baseline_semver", result["blockers"])

    def test_missing_or_untrusted_sha_pins(self):
        for named in ("expected_source_sha256", "expected_qa_sha256",
                      "expected_snapshot_sha256", "expected_qa_provenance_sha256"):
            with self.subTest(pin=named):
                result = self._audit(**{named: None})
                self.assertEqual(result["decision"], "BLOCKED")
        result = self._audit(expected_qa_sha256="0" * 64)
        self.assertEqual(result["checks"]["qa_candidate"]["reason"],
                         "qa_executable_sha256_or_pe_mismatch")
        self.assertIn("external_source_pin",
                      self._audit(expected_source_sha256="0" * 64)["blockers"])
        self.assertEqual(self._audit(expected_qa_provenance_sha256="0" * 64)
                         ["checks"]["qa_candidate"]["reason"],
                         "qa_provenance_sha256_mismatch")

    def test_tampered_versions_block(self):
        mutations = (
            ("package-lock.json", lambda x: x.replace('"1.0.27"', '"1.0.26"', 1),
             "package_lock_version_or_dependency_mismatch"),
            ("madar_update.py", lambda _: 'CURRENT_VERSION = "1.0.26"\n',
             "updater_version_mismatch"),
            ("scripts/build_integrated_v127.py", lambda x: x.replace(
                'builder.VERSION = "1.0.27"', 'builder.VERSION = "1.0.26"'),
             "wrapper_version_mismatch"),
            ("scripts/build_integrated_v127.py", lambda x: x.replace(
                'Madar-Desk-1.0.27-Setup-QA.exe', 'Madar-Desk-1.0.26-Setup-QA.exe'),
             "wrapper_artifact_version_mismatch:builder.QA"),
            ("package.json", lambda x: x.replace(
                "build_integrated_v127.py", "build_integrated_v123.py"),
             "build_route_version_mismatch"),
            ("scripts/build_p0_release_candidate.py", lambda _: "VERSION='1.0.2'\n",
             "inno_version_override_contract_missing"),
        )
        for rel, change, expected in mutations:
            with self.subTest(file=rel):
                path = self.root / rel
                original = path.read_text(encoding="utf-8")
                try:
                    path.write_text(change(original), encoding="utf-8")
                    with self.assertRaisesRegex(mod.ParityError, expected):
                        mod.inspect_source(self.root)
                finally:
                    path.write_text(original, encoding="utf-8")

    def test_bundle_version_and_embedded_provenance_reject(self):
        path = self.bundle / "qa-provenance.json"
        original = path.read_bytes()
        try:
            data = json.loads(original)
            data["appVersion"] = "1.0.26"
            write(self.bundle, "qa-provenance.json", data)
            result = self._audit()
            self.assertIn("qa_candidate", result["blockers"])
            self.assertEqual(result["checks"]["qa_candidate"]["reason"],
                             "qa_provenance_sha256_mismatch")
        finally:
            path.write_bytes(original)

        Archive.data = {**Archive.data, "qa_proof/qa-provenance.json": b"different"}
        result = self._audit()
        self.assertEqual(result["checks"]["qa_candidate"]["reason"],
                         "embedded_qa_provenance_bytes_mismatch")

    def test_latest_user_supplied_qa_pins_and_failsafe_version_block(self):
        bundle = mod.LATEST_QA_BUNDLE
        if not (bundle / "qa-provenance.json").is_file():
            self.skipTest("Newest QA bundle unavailable locally")
        self.assertEqual(mod._file_hash(mod.LATEST_QA_EXE)[0], mod.LATEST_QA_SHA256)
        self.assertEqual(mod._file_hash(bundle / "qa-provenance.json")[0],
                         mod.LATEST_QA_PROVENANCE_SHA256)
        snapshot = mod._json(bundle / "source-input-sha256.json")
        self.assertEqual(snapshot["sourceSnapshotTreeSha256"],
                         mod.LATEST_QA_SNAPSHOT_SHA256)
        result = mod.audit(ROOT, bundle=bundle, qa_artifact=mod.LATEST_QA_EXE,
                           expected_qa_sha256=mod.LATEST_QA_SHA256,
                           expected_qa_provenance_sha256=mod.LATEST_QA_PROVENANCE_SHA256,
                           expected_snapshot_sha256=mod.LATEST_QA_SNAPSHOT_SHA256)
        self.assertEqual(result["decision"], "BLOCKED")
        self.assertIn("no_downgrade", result["blockers"])
        self.assertEqual(result["checks"]["qa_candidate"]["reason"],
                         "missing_or_mismatched_qa_embedded_version")
        self.assertFalse(result["mayInstall"])

    def test_snapshot_drift_and_corrupt_exe_reject(self):
        path = self.root / "native_app.py"
        path.write_text("changed-after-build\n", encoding="utf-8")
        result = self._audit()
        self.assertEqual(result["checks"]["qa_candidate"]["reason"],
                         "source_has_drifted_since_qa_snapshot:native_app.py")
        self.assertEqual(result["decision"], "BLOCKED")
        self.exe.write_bytes(b"bad-header-and-body")
        result = self._audit()
        self.assertEqual(result["checks"]["qa_candidate"]["reason"],
                         "qa_executable_sha256_or_pe_mismatch")

    def test_symlink_is_not_followed(self):
        target = self.root / "package.json"
        duplicate = self.root / "link-package.json"
        try:
            duplicate.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("Windows symlink creation unavailable")
        with self.assertRaisesRegex(mod.ParityError, "linked_or_junction_path"):
            mod._bytes(duplicate)

    def test_real_worktree_metadata_and_baseline_read_only(self):
        paths = [ROOT / rel for rel in (*mod.BASE_FILES,
                                       "scripts/build_integrated_v123.py")]
        before = [(path.stat().st_size, path.stat().st_mtime_ns) for path in paths]
        source = mod.inspect_source(ROOT)
        self.assertEqual(source["version"], "1.0.23")
        result = mod.audit(ROOT)
        self.assertEqual(result["checks"]["source_metadata"]["state"], "PASS")
        self.assertEqual(result["checks"]["no_downgrade"]["state"], "BLOCKED")
        self.assertIn("external_source_pin", result["blockers"])
        self.assertIn("qa_candidate", result["blockers"])
        self.assertEqual(before, [(path.stat().st_size, path.stat().st_mtime_ns)
                                  for path in paths])


if __name__ == "__main__":
    unittest.main()
