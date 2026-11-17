"""Strict Taraz local install probe and deliberate launch, synthetic only."""
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import mtr_taraz_installed_peer as peer
import native_app


class InstalledTarazPeerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mtr-peer-install-qa-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.local = self.root / "Local"
        self.taraz = self.local / "Programs" / "Taraz"
        self.exe = self.taraz / "versions" / "1.0.0" / "Taraz.exe"
        self.exe.parent.mkdir(parents=True)
        self.exe.write_bytes(b"MZ" + b"\0" * 1_100_000)
        self.digest = hashlib.sha256(self.exe.read_bytes()).hexdigest()
        (self.taraz / "current-version.txt").write_text("1.0.0\n", encoding="utf-8")
        env = patch.dict(os.environ, {"LOCALAPPDATA": str(self.local)})
        env.start()
        self.addCleanup(env.stop)
        approved = patch.dict(peer._APPROVED, {"1.0.0": self.digest})
        approved.start()
        self.addCleanup(approved.stop)

    def test_probe_matches_hash_but_does_not_call_taraz(self):
        with patch.object(peer.subprocess, "Popen") as proc:
            result = peer.local_peer_status()
            self.assertEqual(result["version"], "1.0.0")
            self.assertTrue(result["installed"])
            self.assertTrue(result["canOpenManually"])
            self.assertFalse(result["peerAuthenticated"])
            self.assertFalse(result["financialPostingEnabled"])
            self.assertEqual(native_app.Bridge.tarazIntegrationStatus(None)["localPeer"], result)
            proc.assert_not_called()

    def test_manual_launch_only_and_no_finance_claim(self):
        with patch.object(peer.subprocess, "Popen") as proc:
            with self.assertRaises(PermissionError):
                peer.open_local_taraz(manual_action=False)
            with self.assertRaises(PermissionError):
                native_app.Bridge.tarazIntegrationOpenLocal(None)
            proc.assert_not_called()
            result = native_app.Bridge.tarazIntegrationOpenLocal(None, True)
            self.assertEqual(result, {"launchRequested": True, "version": "1.0.0",
                                      "peerAuthenticated": False,
                                      "financialEventCreated": False})
            arguments, kwargs = proc.call_args
            self.assertEqual(arguments, ([str(self.exe)],))
            self.assertEqual(kwargs["cwd"], str(self.exe.parent))
            self.assertNotIn("shell", kwargs)

    def test_changed_binary_fails_closed_and_never_launches(self):
        self.exe.write_bytes(b"MZ" + b"X" * 1_100_000)
        result = peer.local_peer_status()
        self.assertFalse(result["approvedBuild"])
        with patch.object(peer.subprocess, "Popen") as proc:
            with self.assertRaises(peer.TarazPeerUnavailable):
                peer.open_local_taraz(manual_action=True)
            proc.assert_not_called()

    def test_invalid_version_pointer_does_not_use_arbitrary_path(self):
        pointer = self.taraz / "current-version.txt"
        for value in ("../1.0.0", "1.0.0/../../", "99.99.99", "", "1.0.0\n1.0.0"):
            with self.subTest(value=value):
                pointer.write_text(value, encoding="utf-8")
                self.assertFalse(peer.local_peer_status()["canOpenManually"])

    def test_missing_exe_and_version_are_denied(self):
        self.exe.unlink()
        self.assertFalse(peer.local_peer_status()["installed"])
        with self.assertRaises((peer.TarazPeerUnavailable, OSError)):
            peer.open_local_taraz(manual_action=True)

    def test_symlinked_executable_is_rejected(self):
        target = self.root / "other.exe"
        target.write_bytes(self.exe.read_bytes())
        self.exe.unlink()
        try:
            self.exe.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("link creation unavailable")
        self.assertFalse(peer.local_peer_status()["canOpenManually"])

    def test_symlinked_version_pointer_is_rejected(self):
        pointer = self.taraz / "current-version.txt"
        destination = self.root / "pointer.txt"
        destination.write_text("1.0.0", encoding="utf-8")
        pointer.unlink()
        try:
            pointer.symlink_to(destination)
        except (OSError, NotImplementedError):
            self.skipTest("link creation unavailable")
        self.assertFalse(peer.local_peer_status()["approvedBuild"])


if __name__ == "__main__":
    unittest.main()
