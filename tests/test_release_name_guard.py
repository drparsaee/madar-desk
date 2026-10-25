import tempfile
import unittest
from pathlib import Path

from scripts.ensure_new_release import ensure_new_release


class ReleaseNameGuardTests(unittest.TestCase):
    def test_name_must_be_fresh_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            name = "Madar-v10-new.exe"
            candidate = ensure_new_release(name, root)
            self.assertEqual(candidate, root / name)
            self.assertFalse(candidate.exists())
            candidate.write_bytes(b"old release")
            with self.assertRaises(FileExistsError):
                ensure_new_release(name, root)
            self.assertEqual(candidate.read_bytes(), b"old release")

    def test_traversal_and_non_executable_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("../release.exe", "elsewhere/release.exe", "release.zip", "some\\release.exe"):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    ensure_new_release(name, tmp)
