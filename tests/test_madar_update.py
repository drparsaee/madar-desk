"""No network, GitHub credentials, user profiles, SCM or application installs."""
import hashlib
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import madar_update as update


class UpdateSafetyTests(unittest.TestCase):
    def release(self, version="1.0.11", blob=b"MZ" + b"a" * 512):
        return {"tag_name": "v" + version, "draft": False, "prerelease": False,
                "assets": [{"name": f"Madar-Desk-{version}-Setup.exe",
                            "browser_download_url": f"https://github.com/{update.REPOSITORY}/releases/download/v{version}/Madar-Desk-{version}-Setup.exe",
                            "digest": "sha256:" + hashlib.sha256(blob).hexdigest(),
                            "size": len(blob)}]}

    def test_stable_release_and_digest_required(self):
        info = update.inspect_release(self.release())
        self.assertTrue(info["available"])
        self.assertEqual(info["latest"], "1.0.11")
        self.assertFalse(update.inspect_release(self.release("1.0.8"))["available"])
        self.assertFalse(update.inspect_release(self.release("1.0.9"))["available"])
        for bad in ("digest", "browser_download_url", "size"):
            document = self.release()
            document["assets"][0][bad] = None
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                update.inspect_release(document)

    def test_no_untrusted_url_and_no_profile_mutation(self):
        info = update.inspect_release(self.release())
        info["url"] = "https://evil.example.com/f.exe"
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                update.download(info, temporary)
            self.assertFalse(list(Path(temporary).iterdir()))

    def test_download_verifies_exact_size_digest_and_pe(self):
        blob = b"MZ" + b"a" * 512
        info = update.inspect_release(self.release(blob=blob))

        class Response:
            def __init__(self, content):
                from io import BytesIO
                self.stream = BytesIO(content)
            def __enter__(self): return self
            def __exit__(self, *_): self.stream.close()
            def read(self, size): return self.stream.read(size)
            def geturl(self): return info["url"]

        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(update, "urlopen", return_value=Response(blob)):
                result = update.download(info, temporary)
            target = Path(result["path"])
            self.assertTrue(result["verified"])
            self.assertEqual(target.read_bytes(), blob)
            target.unlink()
            with patch.object(update, "urlopen", return_value=Response(blob + b"corruption")):
                with self.assertRaises(ValueError):
                    update.download(info, temporary)
            self.assertFalse(list(Path(temporary).iterdir()))


if __name__ == "__main__":
    unittest.main()
