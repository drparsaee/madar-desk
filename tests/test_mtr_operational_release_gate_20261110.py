"""Offline negative/positive verifier tests; NEVER release or install anything.

Nine private signing keys below are GENERATED only inside disposable temporary
directories by the locally installed OpenSSL CLI. They exist for synthetic
test proofs, not for signing Madar, Taraz, receipts, or production programs.
No actual operational evidence or trusted issuer is simulated as production.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import mtr_operational_release_gate_20261110 as gate


NOW = datetime(2026, 11, 10, 14, 0, tzinfo=timezone.utc)
SUBJECT = {
    "sourceCommit": "a" * 40,
    "sourceSnapshotSha256": "b" * 64,
    "artifactSha256": "c" * 64,
    "appVersion": "1.0.27",
    "sourceInventorySha256": "f" * 64,
    "authenticodeSignerThumbprint": "a" * 40,
}
RUN = "synthetic-audit-run-20261110"


class SignedProofSyntheticFixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        openssl = shutil.which("openssl")
        if not openssl and os.name == "nt":
            candidate = Path(r"C:\Program Files\Git\usr\bin\openssl.exe")
            if candidate.is_file():
                openssl = str(candidate)
        if openssl is None:
            raise unittest.SkipTest("Locally installed OpenSSL needed for synthetic RSA proof fixtures")
        cls.openssl = openssl
        cls.keys_tmp = tempfile.TemporaryDirectory(prefix="mtr-release-testkeys-")
        cls.private = {}
        cls.anchors = {}
        for kind in gate.REQUIRED_KINDS:
            key_id = "synthetic-" + kind + "-authority"
            file = Path(cls.keys_tmp.name) / (kind + ".pem")
            created = subprocess.run(
                [openssl, "genpkey", "-algorithm", "RSA",
                 "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(file)],
                stdin=subprocess.DEVNULL, capture_output=True, timeout=30,
                check=False,
            )
            if created.returncode:
                raise RuntimeError("Cannot create disposable test-only RSA key")
            info = subprocess.run(
                [openssl, "rsa", "-in", str(file), "-text", "-noout"],
                capture_output=True, timeout=15, check=True, text=True,
            ).stdout
            found = re.search(r"modulus:\s*(.*?)\s*publicExponent:", info, flags=re.S)
            if found is None:
                raise RuntimeError("Unexpected OpenSSL test-key text format")
            number = int(re.sub(r"[^0-9a-fA-F]", "", found.group(1)), 16)
            cls.private[kind] = file
            cls.anchors[key_id] = {"n": number, "e": 65537,
                                   "role": gate.ROLES[kind]}

    @classmethod
    def tearDownClass(cls):
        cls.keys_tmp.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="mtr-operation-proof-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.proofs = []
        for kind in gate.REQUIRED_KINDS:
            facts = {
                "source": {"sourceInventorySha256": SUBJECT["sourceInventorySha256"]},
                "build": {"installerSha256": SUBJECT["artifactSha256"],
                          "releaseManifestSha256": "e" * 64},
                "tests": {"executedTests": 2500, "passedAcGates": 40},
                "peer": {"tarazPeerCertificateSha256": "e" * 64,
                         "hostCertificateSha256": "d" * 64},
                "crash": {"testedCrashPoints": 8},
                "backup": {"restoredScopeCount": 7},
                "finance": {"officialReceiptId": "synthetic-receipt-id",
                            "officialDocumentId": "synthetic-document-id"},
                "rollback": {"installedBaselineVersion": "1.0.26",
                             "restoredFilesCount": 100},
                "signing": {"authenticodeSignerThumbprint":
                            SUBJECT["authenticodeSignerThumbprint"],
                            "signedInstallerSha256": SUBJECT["artifactSha256"]},
            }[kind]
            witnesses = {}
            for witness in gate.WITNESS_NAMES[kind]:
                filename = kind + "." + witness + ".json"
                contents = gate._canonical({
                    "schema": 1, "kind": kind, "witness": witness,
                    "scope": "SYNTHETIC_TEST_ONLY",
                    "sourceSha256": SUBJECT["sourceSnapshotSha256"],
                    "artifactSha256": SUBJECT["artifactSha256"],
                })
                (self.root / filename).write_bytes(contents)
                witnesses[filename] = hashlib.sha256(contents).hexdigest()
            detail = {
                "schema": 1, "kind": kind, "runId": RUN,
                "sourceCommit": SUBJECT["sourceCommit"],
                "sourceSha256": SUBJECT["sourceSnapshotSha256"],
                "artifactSha256": SUBJECT["artifactSha256"],
                "appVersion": SUBJECT["appVersion"],
                "checks": {name: True for name in gate.DETAIL_CHECKS[kind]},
                "facts": facts,
                "witnessFiles": witnesses,
            }
            detail_bytes = gate._canonical(detail)
            (self.root / (kind + ".json")).write_bytes(detail_bytes)
            proof = {
                "schema": 1, "kind": kind, "role": gate.ROLES[kind],
                "keyId": "synthetic-" + kind + "-authority",
                "runId": RUN, "issuedUtc": "2026-11-10T13:00:00Z",
                "expiresUtc": "2026-11-11T13:00:00Z",
                "sourceCommit": SUBJECT["sourceCommit"],
                "sourceSha256": SUBJECT["sourceSnapshotSha256"],
                "artifactSha256": SUBJECT["artifactSha256"],
                "appVersion": SUBJECT["appVersion"],
                "evidenceSha256": hashlib.sha256(detail_bytes).hexdigest(),
            }
            self.sign(proof)
            self.proofs.append(proof)
        self.save()

    def sign(self, proof):
        unsigned = {k: v for k, v in proof.items() if k != "signature"}
        done = subprocess.run(
            [self.openssl, "dgst", "-sha256", "-sign",
             str(self.private[proof["kind"]])],
            input=gate._canonical(unsigned), capture_output=True,
            timeout=10, check=True,
        )
        proof["signature"] = done.stdout.hex()

    def save(self):
        (self.root / "proofs.json").write_bytes(
            gate._canonical({"schema": 1, "proofs": self.proofs}))

    def verify(self, *, evidence=None, anchors=None, now=NOW):
        return gate._verify_proofs(self.root if evidence is None else evidence,
                                   anchors=self.anchors if anchors is None else anchors,
                                   expected=SUBJECT, now=now)

    def test_valid_independent_proofs_require_nine_distinct_public_keys(self):
        result = self.verify()
        self.assertEqual(result["verifiedProofCount"], 9)
        self.assertEqual(result["independentIssuerCount"], 9)
        self.assertEqual(result["runId"], RUN)
        self.assertEqual(len({x["n"] for x in self.anchors.values()}), 9)

    def test_owner_unsigned_qa_policy_accepts_only_eight_signed_domains(self):
        self.proofs = [proof for proof in self.proofs if proof["kind"] != "signing"]
        self.save()
        (self.root / "signing.json").unlink()
        for witness in gate.WITNESS_NAMES["signing"]:
            (self.root / ("signing." + witness + ".json")).unlink()
        result = gate._verify_proofs(
            self.root, anchors=self.anchors, expected=SUBJECT, now=NOW,
            required_kinds=gate.OWNER_UNSIGNED_QA_KINDS)
        self.assertEqual(result["verifiedProofCount"], 8)
        with self.assertRaisesRegex(gate.GateError, "proof_count_missing_or_extra"):
            self.verify()

    def test_unsigned_qa_policy_cannot_relabel_production_proofs(self):
        with self.assertRaisesRegex(gate.GateError,
                                    "unsupported_attestation_policy"):
            gate._verify_proofs(
                self.root, anchors=self.anchors, expected=SUBJECT, now=NOW,
                required_kinds=("finance",))

    def test_no_production_keys_or_untrusted_proof_keys(self):
        self.assertEqual(gate.PRODUCTION_TRUST_ANCHORS, {})
        with self.assertRaisesRegex(gate.GateError,
                                    "independent_trust_anchors_not_provisioned"):
            self.verify(anchors={})
        # A key smuggled into the proof file is forbidden, not trust-on-first-use.
        self.proofs[0]["publicKey"] = "synthetic-untrusted"
        self.save()
        with self.assertRaisesRegex(gate.GateError, "extra_or_missing_proof_fields"):
            self.verify()

    def test_forged_signature_and_unsigned_claim_changes_are_rejected(self):
        self.proofs[0]["signature"] = "00" * 256
        self.save()
        with self.assertRaisesRegex(gate.GateError, "invalid_independent_signature"):
            self.verify()
        self.proofs[0]["signature"] = self.proofs[1]["signature"]
        self.save()
        with self.assertRaisesRegex(gate.GateError, "invalid_independent_signature"):
            self.verify()

    def test_signed_but_stale_future_expired_and_wrong_epoch_proofs_rejected(self):
        for issued, expired, message in (
            ("2026-11-07T00:00:00Z", "2026-11-10T15:00:00Z", "stale"),
            ("2026-11-10T16:00:00Z", "2026-11-11T16:00:00Z", "future"),
            ("2026-11-09T12:00:00Z", "2026-11-10T13:30:00Z", "expired"),
            ("2026-11-10T13:00:00+00:00", "2026-11-11T13:00:00Z", "utc"),
        ):
            with self.subTest(reason=message):
                original = deepcopy(self.proofs[0])
                self.proofs[0]["issuedUtc"] = issued
                self.proofs[0]["expiresUtc"] = expired
                self.sign(self.proofs[0])
                self.save()
                with self.assertRaisesRegex(gate.GateError,
                                            "stale_future_or_expired|strict_utc"):
                    self.verify()
                self.proofs[0] = original

    def test_missing_proof_row_fails_closed(self):
        self.proofs.pop()
        self.save()
        with self.assertRaisesRegex(gate.GateError, "proof_count_missing_or_extra"):
            self.verify()

    def test_extra_proof_row_fails_closed(self):
        self.proofs.append(deepcopy(self.proofs[0]))
        self.save()
        with self.assertRaisesRegex(gate.GateError, "proof_count_missing_or_extra"):
            self.verify()

    def test_duplicate_kind_replacing_another_fails_closed(self):
        self.proofs[-1] = deepcopy(self.proofs[0])
        self.save()
        with self.assertRaisesRegex(gate.GateError, "unknown_or_duplicate_proof_kind"):
            self.verify()

    def test_unknown_kind_replacing_valid_row_fails_closed(self):
        self.proofs[0]["kind"] = "unknown"
        self.save()
        with self.assertRaisesRegex(gate.GateError, "unknown_or_duplicate_proof_kind"):
            self.verify()

    def test_extra_or_missing_disk_proof_files_fail_closed(self):
        (self.root / "fake.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(gate.GateError, "proof_files_missing_or_extra"):
            self.verify()
        (self.root / "fake.json").unlink()
        (self.root / "backup.json").unlink()
        with self.assertRaisesRegex(gate.GateError, "proof_files_missing_or_extra"):
            self.verify()

    def test_duplicate_json_manifest_key_rejected(self):
        content = (self.root / "proofs.json").read_text(encoding="utf-8")
        (self.root / "proofs.json").write_text(
            content.replace('"schema":1', '"schema":1,"schema":1', 1),
            encoding="utf-8")
        with self.assertRaisesRegex(gate.GateError, "duplicate_json_key"):
            self.verify()

    def test_signing_does_not_authorize_changed_witness(self):
        file = self.root / "finance.json"
        data = json.loads(file.read_text(encoding="utf-8"))
        data["checks"]["officialLedgerReadbackMatched"] = False
        file.write_bytes(gate._canonical(data))
        with self.assertRaisesRegex(gate.GateError, "witness_detail_digest_mismatch"):
            self.verify()

    def test_separately_hashed_witness_file_changed_is_blocked(self):
        file = self.root / "finance.official-taraz-receipt.json"
        file.write_bytes(file.read_bytes() + b"\n")
        with self.assertRaisesRegex(gate.GateError,
                                    "independent_witness_file_hash_mismatch"):
            self.verify()

    def test_signed_finance_without_official_receipt_id_is_blocked(self):
        kind = "finance"
        file = self.root / (kind + ".json")
        data = json.loads(file.read_text(encoding="utf-8"))
        data["facts"]["officialReceiptId"] = ""
        body = gate._canonical(data)
        file.write_bytes(body)
        proof = next(item for item in self.proofs if item["kind"] == kind)
        proof["evidenceSha256"] = hashlib.sha256(body).hexdigest()
        self.sign(proof)
        self.save()
        with self.assertRaisesRegex(gate.GateError,
                                    "official_financial_reference_missing"):
            self.verify()

    def test_stale_rollback_baseline_downgrade_fails(self):
        kind = "rollback"
        file = self.root / (kind + ".json")
        data = json.loads(file.read_text(encoding="utf-8"))
        data["facts"]["installedBaselineVersion"] = "1.0.27"
        body = gate._canonical(data)
        file.write_bytes(body)
        proof = next(item for item in self.proofs if item["kind"] == kind)
        proof["evidenceSha256"] = hashlib.sha256(body).hexdigest()
        self.sign(proof)
        self.save()
        with self.assertRaisesRegex(gate.GateError,
                                    "rollback_target_not_older_than_candidate"):
            self.verify()

    def test_forged_signer_thumbprint_even_if_signed_is_blocked(self):
        kind = "signing"
        file = self.root / (kind + ".json")
        data = json.loads(file.read_text(encoding="utf-8"))
        data["facts"]["authenticodeSignerThumbprint"] = "b" * 40
        body = gate._canonical(data)
        file.write_bytes(body)
        proof = next(item for item in self.proofs if item["kind"] == kind)
        proof["evidenceSha256"] = hashlib.sha256(body).hexdigest()
        self.sign(proof)
        self.save()
        with self.assertRaisesRegex(gate.GateError,
                                    "signed_publisher_identity_mismatch"):
            self.verify()

    def test_signed_failing_evidence_never_counts_as_pass(self):
        kind = "finance"
        file = self.root / (kind + ".json")
        data = json.loads(file.read_text(encoding="utf-8"))
        data["checks"]["officialLedgerReadbackMatched"] = False
        data_bytes = gate._canonical(data)
        file.write_bytes(data_bytes)
        proof = next(item for item in self.proofs if item["kind"] == kind)
        proof["evidenceSha256"] = hashlib.sha256(data_bytes).hexdigest()
        self.sign(proof)
        self.save()
        with self.assertRaisesRegex(gate.GateError,
                                    "failed_or_incomplete_operational_witness"):
            self.verify()

    def test_signed_unknown_extra_or_omitted_witness_check_denied(self):
        kind = "rollback"
        file = self.root / (kind + ".json")
        proof = next(item for item in self.proofs if item["kind"] == kind)
        before = json.loads(file.read_text(encoding="utf-8"))
        for data in ({**before, "checks": {**before["checks"], "fake": True}},
                     {**before, "checks": {
                         k: v for k, v in before["checks"].items()
                         if k != "rollbackRestoresAllState"}}):
            with self.subTest(checks=list(data["checks"])):
                body = gate._canonical(data)
                file.write_bytes(body)
                proof["evidenceSha256"] = hashlib.sha256(body).hexdigest()
                self.sign(proof)
                self.save()
                with self.assertRaisesRegex(gate.GateError,
                                            "failed_or_incomplete_operational_witness"):
                    self.verify()

    def test_wrong_signed_subject_or_mismatched_run_denied(self):
        self.proofs[0]["appVersion"] = "1.0.26"
        self.sign(self.proofs[0])
        self.save()
        with self.assertRaisesRegex(gate.GateError, "stale_or_foreign_attestation_subject"):
            self.verify()
        self.proofs[0]["appVersion"] = SUBJECT["appVersion"]
        self.proofs[0]["runId"] = "another-synthetic-run"
        self.sign(self.proofs[0])
        self.save()
        with self.assertRaisesRegex(gate.GateError,
                                    "witness_subject_disagreement"):
            self.verify()

    def test_reused_signer_key_or_wrong_role_denied(self):
        second = self.proofs[1]
        original = self.anchors[second["keyId"]]
        self.anchors[second["keyId"]] = {
            "n": self.anchors[self.proofs[0]["keyId"]]["n"], "e": 65537,
            "role": gate.ROLES[second["kind"]]}
        with self.assertRaisesRegex(gate.GateError, "shared_public_key"):
            self.verify()
        self.anchors[second["keyId"]] = original
        self.proofs[0]["role"] = gate.ROLES["rollback"]
        self.sign(self.proofs[0])
        self.save()
        with self.assertRaisesRegex(gate.GateError, "incorrect_role"):
            self.verify()

    def test_missing_issuer_and_corrupt_anchor_denied(self):
        anchors = {k: v for k, v in self.anchors.items() if
                   k != self.proofs[0]["keyId"]}
        with self.assertRaisesRegex(gate.GateError, "unknown_or_reused_issuer"):
            self.verify(anchors=anchors)
        anchors = dict(self.anchors)
        key = self.proofs[0]["keyId"]
        anchors[key] = {**anchors[key], "n": 3}  # Invalid short RSA key.
        with self.assertRaisesRegex(gate.GateError, "invalid_independent_signature"):
            self.verify(anchors=anchors)

    def test_forged_source_reference_and_symlink_witness_denied(self):
        self.proofs[0]["sourceSha256"] = "e" * 64
        self.sign(self.proofs[0])
        self.save()
        with self.assertRaisesRegex(gate.GateError, "stale_or_foreign_attestation_subject"):
            self.verify()
        self.proofs[0]["sourceSha256"] = SUBJECT["sourceSnapshotSha256"]
        self.sign(self.proofs[0])
        self.save()
        other = tempfile.TemporaryDirectory(prefix="mtr-nonproof-target-")
        self.addCleanup(other.cleanup)
        external = Path(other.name) / "other.json"
        external.write_text("{}", encoding="utf-8")
        original = self.root / "source.json"
        original.unlink()
        try:
            original.symlink_to(external)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink support restricted on this host")
        with self.assertRaisesRegex(gate.GateError, "linked_input|symlink_or_junction"):
            self.verify()


class RealQABundleCannotAuthorizeRelease(unittest.TestCase):
    def test_cli_current_workspace_is_hard_no_go(self):
        completed = subprocess.run(
            [sys.executable, "-B", str(gate.SOURCE / "tools" /
             "mtr_operational_release_gate_20261110.py")],
            capture_output=True, text=True, timeout=110, check=False,
        )
        self.assertEqual(completed.returncode, 2, completed.stderr)
        parsed = json.loads(completed.stdout)
        self.assertEqual(parsed["decision"], "NO_GO")
        self.assertFalse(parsed["mayInstall"])
        self.assertFalse(parsed["mayDeploy"])
        self.assertEqual(parsed["checks"]["exact_snapshot"]["state"], "PASS")
        self.assertEqual(parsed["checks"]["complete_qa_bundle"]["state"], "PASS")
        self.assertEqual(parsed["checks"]["release_quality_artifact"]["state"],
                         "BLOCKED")
        self.assertEqual(parsed["checks"]["source_version"]["appVersion"],
                         "1.0.23")
        self.assertIn("app_version_alignment", parsed["blockers"])
        self.assertEqual(parsed["checks"]["authenticode"]["status"], "NotSigned")
        self.assertIn("independent_operational_attestations", parsed["blockers"])
        self.assertIn("operational_proof_inventory", parsed["blockers"])

    def test_explicit_owner_unsigned_qa_gate_is_not_production_release(self):
        completed = subprocess.run(
            [sys.executable, "-B", str(gate.SOURCE / "tools" /
             "mtr_operational_release_gate_20261110.py"), "--policy",
             "owner-controlled-unsigned-qa"],
            capture_output=True, text=True, timeout=110, check=False,
        )
        self.assertEqual(completed.returncode, 2, completed.stderr)
        parsed = json.loads(completed.stdout)
        self.assertEqual(parsed["policy"], "owner-controlled-unsigned-qa")
        self.assertTrue(parsed["signingDeferredForOwnerQaOnly"])
        self.assertFalse(parsed["mayInstall"])
        self.assertFalse(parsed["mayDeploy"])
        self.assertEqual(parsed["decision"], "NO_GO")
        self.assertEqual(parsed["checks"]["authenticode"]["state"], "PASS")
        self.assertEqual(parsed["checks"]["authenticode"]["status"], "NotSigned")
        self.assertFalse(
            parsed["checks"]["authenticode"]["signedDistributionApproved"])
        self.assertEqual(parsed["checks"]["release_quality_artifact"]["state"],
                         "PASS")
        self.assertIn("app_version_alignment", parsed["blockers"])
        self.assertIn("clean_committed_source", parsed["blockers"])
        self.assertIn("operational_proof_inventory", parsed["blockers"])
        self.assertIn("independent_operational_attestations", parsed["blockers"])

    def test_strict_versions_and_relative_escape_inputs_are_refused(self):
        for value in ("1.0.27-rc", "01.0.26", "1.0", "bad", "1.0.27.0"):
            with self.subTest(value=value):
                with self.assertRaises(gate.GateError):
                    gate._version(value)
        with tempfile.TemporaryDirectory(prefix="mtr-gate-safe-relative-") as td:
            root = Path(td)
            for rel in ("../outside", "/absolute", "sub/../../escape", "foo\\bar",
                        "sub//file", "./file"):
                with self.subTest(relative=rel):
                    with self.assertRaises(gate.GateError):
                        gate._inside(root, rel)

    def test_no_production_attester_can_be_user_provided_through_cli(self):
        self.assertEqual(gate.PRODUCTION_TRUST_ANCHORS, {})
        self.assertFalse(hasattr(gate, "sign_proof"))
        self.assertFalse(hasattr(gate, "issue_proof"))
        self.assertFalse(hasattr(gate, "install_release"))
        parser_source = (gate.SOURCE / "tools" /
                         "mtr_operational_release_gate_20261110.py").read_text(
                             encoding="utf-8")
        self.assertNotIn('parser.add_argument("--trust-anchors"', parser_source)
        self.assertNotIn('parser.add_argument("--allow-unsigned"', parser_source)


if __name__ == "__main__":
    unittest.main()
