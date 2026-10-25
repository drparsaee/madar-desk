"""Windows-only portable install/update tests, never touching user APPDATA.

Synthetic non-runnable PE binaries exercise header/hash checks. All write
targets are under a disposable test root inside the Madar project workspace.
"""
import ctypes
from ctypes import wintypes
import hashlib
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "Install-MadarDesk.ps1"


def synthetic_pe(version: int) -> bytes:
    """PE32+ header with one COFF section; deliberately NOT executable code."""
    data = bytearray(1024)
    data[0:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", data, 0x84, 0x8664)  # x64 machine
    struct.pack_into("<H", data, 0x86, 1)       # one section
    struct.pack_into("<H", data, 0x94, 240)     # PE32+ optional header size
    struct.pack_into("<H", data, 0x96, 0x0022)
    struct.pack_into("<H", data, 0x98, 0x20B)   # PE32+
    struct.pack_into("<I", data, 0x220, version)
    return bytes(data)


@unittest.skipUnless(sys.platform == "win32", "Requires Windows PowerShell 5.1")
class PortableInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".madar-portable-inst-test-",
                                                dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source" / "Madar-Desk-v1.0-rc1.exe"
        self.source.parent.mkdir()
        self.source.write_bytes(synthetic_pe(100))
        self.install = self.root / "portable-app"
        self.data = self.root / "state-data" / "Madar Desk"
        self.data.mkdir(parents=True)
        self.marker = self.data / "private-user-data.db"
        self.marker.write_bytes(b"DO NOT TOUCH USER DATA")

    def shell(self, *, source=None, destination=None, expected=None,
              extra=(), environment=None):
        target = self.install if destination is None else destination
        cmd = [
            "powershell.exe", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
            "-SourceExe", str(self.source if source is None else source),
            "-InstallDir", str(target),
        ]
        if expected is not None:
            cmd.extend(["-ExpectedSha256", str(expected)])
        cmd.extend(extra)
        env = os.environ.copy()
        env["APPDATA"] = str(self.root / "state-data")
        env["LOCALAPPDATA"] = str(self.root / "state-local")
        env["PROGRAMDATA"] = str(self.root / "state-program")
        env["TEMP"] = str(self.root)
        env["TMP"] = str(self.root)
        env.update(environment or {})
        return subprocess.run(cmd, cwd=self.root, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True, errors="replace",
                              timeout=20)

    def assertClean(self):
        self.assertFalse((self.install / ".madar-portable-install.lock").exists())
        self.assertEqual(list(self.install.glob(".Madar-Desk.stage.*.exe")), [])
        self.assertEqual(self.marker.read_bytes(), b"DO NOT TOUCH USER DATA")

    def test_fresh_portable_install_creates_only_exe(self):
        payload = self.source.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        result = self.shell(expected=digest.upper())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.install / "Madar-Desk.exe").read_bytes(), payload)
        self.assertEqual(self.source.read_bytes(), payload)
        self.assertEqual(list(self.install.glob("Madar-Desk.backup.*.exe")), [])
        # PowerShell's auto-table renderer may shorten the SHA256 column to
        # only eight hex digits plus "...", depending on console width.
        # Exact installed bytes were already compared to the source above;
        # assert only the visible prefix in human-readable installer output.
        self.assertIn(digest[:8], result.stdout.lower())
        self.assertClean()

    def test_updates_preserve_all_prior_backups_and_unrelated_artifacts(self):
        self.install.mkdir()
        other = self.install / "Madar-Desk-v0.2-old-release.exe"
        other.write_bytes(b"UNRELATED OLD RELEASE")
        initial = synthetic_pe(1)
        self.install.joinpath("Madar-Desk.exe").write_bytes(initial)
        self.source.write_bytes(synthetic_pe(2))
        first = self.shell()
        self.assertEqual(first.returncode, 0, first.stderr)
        backups = list(self.install.glob("Madar-Desk.backup.*.exe"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), initial)
        second_old = synthetic_pe(2)
        self.source.write_bytes(synthetic_pe(3))
        second = self.shell()
        self.assertEqual(second.returncode, 0, second.stderr)
        next_backups = list(self.install.glob("Madar-Desk.backup.*.exe"))
        self.assertEqual(len(next_backups), 2)
        self.assertEqual({path.read_bytes() for path in next_backups},
                         {initial, second_old})
        self.assertEqual((self.install / "Madar-Desk.exe").read_bytes(),
                         synthetic_pe(3))
        self.assertEqual(other.read_bytes(), b"UNRELATED OLD RELEASE")
        self.assertClean()

    def test_expected_sha256_mismatch_is_preflight_and_does_not_mutate(self):
        result = self.shell(expected="0" * 64)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.install.exists())
        self.assertEqual(self.marker.read_bytes(), b"DO NOT TOUCH USER DATA")

    def test_invalid_pe_and_wrong_extension_fail_before_creating_directory(self):
        variants = (
            b"not exe" + b"\0" * 1000,
            b"MZ" + b"\0" * 1022,  # e_lfanew=0
            synthetic_pe(1)[:0x80] + b"BAD!" + synthetic_pe(1)[0x84:],
            synthetic_pe(1)[:0x84] + b"\0\0" + synthetic_pe(1)[0x86:],
        )
        for data in variants:
            with self.subTest(prefix=data[:16]):
                self.source.write_bytes(data)
                result = self.shell()
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.install.exists())
        self.source.write_bytes(synthetic_pe(100))
        renamed = self.source.with_suffix(".txt")
        renamed.write_bytes(self.source.read_bytes())
        result = self.shell(source=renamed)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.install.exists())

    def test_existing_non_pe_target_is_never_overwritten(self):
        self.install.mkdir()
        target = self.install / "Madar-Desk.exe"
        target.write_bytes(b"THIS IS NOT AN EXE; IMPORTANT USER FILE")
        result = self.shell()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(target.read_bytes(), b"THIS IS NOT AN EXE; IMPORTANT USER FILE")
        self.assertEqual(list(self.install.glob("*.backup.*.exe")), [])
        self.assertClean()

    def test_preexisting_directory_lock_refuses_without_removing_lock(self):
        self.install.mkdir()
        target = self.install / "Madar-Desk.exe"
        target.write_bytes(synthetic_pe(1))
        lock = self.install / ".madar-portable-install.lock"
        lock.write_text("stale or concurrent owner", encoding="utf8")
        result = self.shell()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(lock.read_text(encoding="utf8"), "stale or concurrent owner")
        self.assertEqual(target.read_bytes(), synthetic_pe(1))
        self.assertEqual(list(self.install.glob(".Madar-Desk.stage.*.exe")), [])
        self.assertEqual(self.marker.read_bytes(), b"DO NOT TOUCH USER DATA")

    def test_rollback_restores_original_byte_for_byte_after_backup(self):
        self.install.mkdir()
        target = self.install / "Madar-Desk.exe"
        original = synthetic_pe(5)
        target.write_bytes(original)
        unrelated = self.install / "old-v1.0-rc1.exe"
        unrelated.write_bytes(synthetic_pe(4))
        fail = self.shell(extra=("-TestFailAfterBackup",))
        self.assertNotEqual(fail.returncode, 0)
        self.assertIn("Injected test failure", fail.stderr)
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(unrelated.read_bytes(), synthetic_pe(4))
        self.assertEqual(list(self.install.glob("Madar-Desk.backup.*.exe")), [])
        self.assertClean()
        success = self.shell()
        self.assertEqual(success.returncode, 0, success.stderr)
        self.assertEqual(len(list(self.install.glob("Madar-Desk.backup.*.exe"))), 1)
        self.assertClean()

    def test_injected_failure_on_fresh_install_leaves_no_target(self):
        failure = self.shell(extra=("-TestFailAfterBackup",))
        self.assertNotEqual(failure.returncode, 0)
        self.assertFalse((self.install / "Madar-Desk.exe").exists())
        self.assertClean()

    def test_failure_after_final_rename_restores_old_exe_and_quarantines_new(self):
        self.install.mkdir()
        old = synthetic_pe(19)
        new = synthetic_pe(20)
        target = self.install / "Madar-Desk.exe"
        target.write_bytes(old)
        self.source.write_bytes(new)
        failure = self.shell(extra=("-TestFailAfterRename",))
        self.assertNotEqual(failure.returncode, 0)
        self.assertEqual(target.read_bytes(), old)
        quarantined = list(self.install.glob("Madar-Desk.failed.*.exe"))
        self.assertEqual(len(quarantined), 1)
        self.assertEqual(quarantined[0].read_bytes(), new)
        self.assertClean()

    def test_failed_first_install_after_final_rename_removes_live_target(self):
        fail = self.shell(extra=("-TestFailAfterRename",))
        self.assertNotEqual(fail.returncode, 0)
        self.assertFalse((self.install / "Madar-Desk.exe").exists())
        quarantined = list(self.install.glob("Madar-Desk.failed.*.exe"))
        self.assertEqual(len(quarantined), 1)
        self.assertEqual(quarantined[0].read_bytes(), self.source.read_bytes())
        self.assertClean()

    def test_reinstall_identical_hash_is_noop_without_generating_backup(self):
        first = self.shell()
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.shell()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(list(self.install.glob("Madar-Desk.backup.*.exe")), [])
        self.assertEqual((self.install / "Madar-Desk.exe").read_bytes(),
                         self.source.read_bytes())
        self.assertClean()

    def test_locked_target_refuses_without_touching_binary(self):
        self.install.mkdir()
        target = self.install / "Madar-Desk.exe"
        payload = synthetic_pe(6)
        target.write_bytes(payload)
        # Windows CreateFile share mode 0 denies even unrelated read/write opens.
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        create = kernel.CreateFileW
        create.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
            wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        create.restype = wintypes.HANDLE
        handle = create(str(target), 0x80000000, 0, None, 3, 0x80, None)
        invalid = ctypes.c_void_p(-1).value
        self.assertNotEqual(handle, invalid, f"CreateFileW failed: {ctypes.get_last_error()}")
        try:
            result = self.shell()
            self.assertNotEqual(result.returncode, 0)
        finally:
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel.CloseHandle(handle)
        self.assertEqual(target.read_bytes(), payload)
        self.assertEqual(list(self.install.glob("Madar-Desk.backup.*.exe")), [])
        self.assertClean()

    def test_source_inside_install_dir_is_rejected_and_not_renamed(self):
        self.install.mkdir()
        source = self.install / "Madar-Desk-v1.0-rc1.exe"
        source.write_bytes(synthetic_pe(8))
        result = self.shell(source=source)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(source.read_bytes(), synthetic_pe(8))
        self.assertFalse((self.install / "Madar-Desk.exe").exists())
        self.assertClean()

    def test_protected_appdata_directory_is_rejected_even_with_valid_exe(self):
        actual_data = self.root / "state-data" / "Madar Desk"
        result = self.shell(destination=actual_data)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((actual_data / "Madar-Desk.exe").exists())
        self.assertEqual(self.marker.read_bytes(), b"DO NOT TOUCH USER DATA")

    def test_drive_root_relative_and_device_install_paths_are_rejected(self):
        for target in (str(self.root.anchor), "relative\\portable",
                       "\\\\server\\share\\portable"):
            with self.subTest(path=target):
                result = self.shell(destination=target)
                self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.marker.read_bytes(), b"DO NOT TOUCH USER DATA")

    def test_synthetic_pe_cannot_be_mistaken_for_trust_or_signature(self):
        # Structural PE checks are necessary but NOT proof of signed/authentic
        # software. The positive suite intentionally tests only header bounds.
        self.assertEqual(self.source.read_bytes()[:2], b"MZ")
        self.assertNotEqual(self.source.read_bytes()[:32], b"Windows signed EXE")
        self.assertRegex(hashlib.sha256(self.source.read_bytes()).hexdigest(),
                         r"^[0-9a-f]{64}$")

    def test_existing_rc_binary_installs_only_to_disposable_location(self):
        release = ROOT / "release" / "Madar-Desk-v1.0-rc1.exe"
        if not release.is_file():
            self.skipTest("Optional RC EXE not built yet; synthetic PE cases still apply")
        original_digest = hashlib.sha256(release.read_bytes()).hexdigest()
        result = self.shell(source=release, expected=original_digest)
        self.assertEqual(result.returncode, 0, result.stderr)
        destination = self.install / "Madar-Desk.exe"
        self.assertEqual(hashlib.sha256(destination.read_bytes()).hexdigest(),
                         original_digest)
        self.assertEqual(hashlib.sha256(release.read_bytes()).hexdigest(),
                         original_digest)
        self.assertClean()


if __name__ == "__main__":
    unittest.main()
