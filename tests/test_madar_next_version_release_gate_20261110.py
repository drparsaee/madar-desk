"""Read-only release gate. Disposable negative cases never launch/modify Madar."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / (
    "scripts/qa_madar_next_version_release_gate_20261110.py")
spec = importlib.util.spec_from_file_location("madar_next_release_gate", SCRIPT)
gate = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(gate)


def write(path: Path, value: str | bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value if isinstance(value, bytes) else value.encode("utf-8"))


def fixture_source(root: Path, version: str):
    write(root / "package.json", json.dumps({"version": version}))
    write(root / "package-lock.json", json.dumps({
        "version": version, "packages": {"": {"version": version}}}))
    write(root / "madar_update.py", f'CURRENT_VERSION = "{version}"\n')
    write(root / "scripts/build_p1p2_v126_qa.py", f'VERSION = "{version}"\n')
    write(root / "scripts/madar-update.iss",
          "EXE_SHA256\nOutputDir=..\\release\nonlyifdoesntexist\n")
    write(root / "scripts/Madar-Activate-Version.ps1",
          "Target program integrity verification failed\n-AllowRollback\n")
    write(root / "scripts/Madar-Upgrade-Preflight.ps1",
          "Snapshot checksum mismatch\n")
    write(root / "scripts/Run-Madar.cmd", "current-version.txt\n")
    return root


def legitimate_structural_evidence():
    return {
        "installed": {"status": "VERIFIED_PE_READ_ONLY",
                      "version": "1.0.26", "readOnly": True},
        "git": {"clean": True, "detached": False},
        "version": {"aligned": True, "strictlyNewer": True},
        "qa": {"status": "PINNED_QA_EMBEDDED_FEATURES_VERIFIED",
               "runtimeMetadataImports": True, "installerVerified": True,
               "releaseSigned": True, "officialFinanceReceiptVerified": True},
        "parity": {"sourceMatchesPackagedNative": True,
                   "metadataImportsPresentInLiveSource": True,
                   "metadataImportsPresentInStage": True,
                   "authenticatedFinanceRuntimeWired": True},
        "candidate": {
            "status": "ARTIFACT_BYTES_MATCH_SELF_DECLARED_MANIFEST_ONLY"}
    }


class ReadOnlyReleaseGateTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(dir=r"D:\CoS-Test",
                                          prefix="mtr-release-gate-synthetic-")
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name)

    def test_installed_v126_reads_only_specific_pointer_and_exe(self):
        installed = self.path / "Programs" / "MadarDesk"
        write(installed / "current-version.txt", "1.0.26\n")
        binary = installed / "versions" / "1.0.26" / "Madar-Desk.exe"
        write(binary, b"MZ" + b"synthetic-pe" * 100)
        user_file = self.path / "MadarDesk" / "tasks.json"
        write(user_file, '{"unchanged":true}')
        original = gate.digest(binary)
        result = gate.installed_baseline(self.path)
        self.assertEqual(result["status"], "VERIFIED_PE_READ_ONLY")
        self.assertEqual(result["version"], "1.0.26")
        self.assertEqual(result["v126ExeSha256"], original)
        self.assertEqual(user_file.read_text(), '{"unchanged":true}')
        self.assertEqual(gate.digest(binary), original)

    def test_broken_installed_pointer_and_unsafe_exe_fail_closed(self):
        installed = self.path / "Programs" / "MadarDesk"
        write(installed / "current-version.txt", "garbage")
        write(installed / "versions" / "1.0.26" / "Madar-Desk.exe",
              b"MZ" + b"x" * 1050)
        self.assertEqual(gate.installed_baseline(self.path)["status"], "BLOCKED")
        write(installed / "current-version.txt", "1.0.26")
        write(installed / "versions" / "1.0.26" / "Madar-Desk.exe",
              b"not-a-PE" * 150)
        self.assertEqual(gate.installed_baseline(self.path)["status"], "BLOCKED")

    def test_versions_monotonic_and_consistent_builder_contract(self):
        source = fixture_source(self.path / "src", "1.0.27")
        good = gate.source_version_contract(source, "1.0.26")
        self.assertTrue(good["aligned"])
        self.assertTrue(good["strictlyNewer"])
        write(source / "madar_update.py", 'CURRENT_VERSION = "1.0.26"')
        mismatched = gate.source_version_contract(source, "1.0.26")
        self.assertFalse(mismatched["aligned"])
        self.assertFalse(mismatched["strictlyNewer"])
        fixture_source(source, "1.0.26")
        same = gate.source_version_contract(source, "1.0.26")
        self.assertTrue(same["aligned"])
        self.assertFalse(same["strictlyNewer"])

    def test_missing_snapshot_or_malformed_candidate_is_blocked(self):
        self.assertEqual(
            gate.verify_qa_provenance(self.path / "none", self.path)["status"],
            "BLOCKED")
        candidate = self.path / "candidate"
        candidate.mkdir()
        write(candidate / "release-evidence.json", "not json")
        self.assertEqual(
            gate.optional_candidate(candidate, {"version": "1.0.26"})["status"],
            "BLOCKED")

    def test_candidate_requires_expected_version_pe_and_integrity(self):
        candidate = self.path / "candidate"
        candidate.mkdir()
        files = {"app": "Madar-Desk.exe",
                 "setup": "Madar-Desk-1.0.27-Setup.exe"}
        for name in files.values():
            write(candidate / name, b"MZ" + b"synthetic" * 130)
        record = {"version": "1.0.27",
                  "artifacts": {k: {"filename": name,
                      "sha256": gate.digest(candidate / name)}
                                for k, name in files.items()}}
        write(candidate / "release-evidence.json", json.dumps(record))
        structurally = gate.optional_candidate(candidate, {"version": "1.0.26"})
        self.assertEqual(structurally["status"],
                         "ARTIFACT_BYTES_MATCH_SELF_DECLARED_MANIFEST_ONLY")
        self.assertFalse(structurally["authenticatedInstallerQA"])
        # A modified file with a stale hash must never be accepted.
        write(candidate / "Madar-Desk.exe", b"MZ" + b"different" * 150)
        self.assertEqual(gate.optional_candidate(
            candidate, {"version": "1.0.26"})["status"], "BLOCKED")
        record["version"] = "1.0.26"
        write(candidate / "release-evidence.json", json.dumps(record))
        self.assertEqual(gate.optional_candidate(
            candidate, {"version": "1.0.26"})["status"], "BLOCKED")

    def test_symlink_candidate_and_profile_candidates_denied(self):
        other = self.path / "other"
        other.mkdir()
        link = self.path / "candidate-link"
        try:
            link.symlink_to(other, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("host cannot create disposable symlink")
        self.assertEqual(gate.optional_candidate(
            link, {"version": "1.0.26"})["status"], "BLOCKED")

    def test_complete_looking_untrusted_inputs_still_no_go_without_verified_e2e(self):
        evidence = legitimate_structural_evidence()
        result = gate.evaluate(override=evidence)
        self.assertEqual(result["status"], "NO_GO")
        self.assertIn("INSTALL_ROLLBACK_RECOVERY_E2E", result["blockers"])
        self.assertIn("GUI_LAN_SECURITY_E2E", result["blockers"])
        self.assertIn("OWNER_RELEASE_APPROVAL", result["blockers"])
        self.assertTrue(all(item["code"] in {a["code"] for a in result["checks"]}
                            for item in result["checks"]))
        self.assertFalse(result["published"])
        self.assertFalse(result["officialFinanceReceiptVerified"])

    def test_unproven_peer_and_finance_are_explicit_release_blockers(self):
        evidence = legitimate_structural_evidence()
        evidence["qa"] = {
            **evidence["qa"], "officialFinanceReceiptVerified": False}
        evidence["parity"] = {
            **evidence["parity"], "authenticatedFinanceRuntimeWired": False}
        result = gate.evaluate(override=evidence)
        self.assertEqual(result["status"], "NO_GO")
        self.assertIn("AUTHENTICATED_PEER_FINANCE", result["blockers"])

    def test_real_pinned_qa_is_inspectable_but_not_new_release(self):
        result = gate.verify_qa_provenance(gate.VITE_QA, gate.EXE_QA)
        self.assertEqual(result["status"],
                         "PINNED_QA_EMBEDDED_FEATURES_VERIFIED")
        self.assertTrue(result["runtimeMetadataImports"])
        self.assertFalse(result["installerVerified"])
        self.assertFalse(result["releaseSigned"])
        self.assertFalse(result["officialFinanceReceiptVerified"])
        self.assertEqual(result["qaVersion"], "1.0.26")

    def test_local_source_contract_still_v126_and_dirty(self):
        installed = gate.installed_baseline()
        self.assertEqual(installed.get("status"), "VERIFIED_PE_READ_ONLY")
        version = gate.source_version_contract(gate.SOURCE, installed["version"])
        self.assertTrue(version["aligned"])
        self.assertFalse(version["strictlyNewer"])
        git = gate.git_state(gate.SOURCE)
        self.assertFalse(git["clean"])
        self.assertGreater(git["dirtyCount"], 0)


if __name__ == "__main__":
    unittest.main()
