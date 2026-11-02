"""Brand file contract. Visual artwork is supplied by the application owner."""

import hashlib
from pathlib import Path
import unittest
from xml.etree import ElementTree

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


class MadarBrandIconContract(unittest.TestCase):
    def test_svg_paths_match_uploaded_artwork_and_ui_is_same_master(self):
        source = (ROOT / "assets/madar-final.svg").read_bytes()
        self.assertEqual(source, (ROOT / "public/madar-icon.svg").read_bytes())
        root = ElementTree.fromstring(source)
        self.assertEqual(root.get("viewBox"), "0 0 340.16 340.16")
        self.assertEqual(
            [hashlib.sha256(node.get("d").encode("utf8")).hexdigest()[:16]
             for node in root.findall(".//{*}path")],
            ["117cd8a9e0c733f8", "ed345336720e59d4",
             "c48ce0eb51393311", "e5bc5c54c45ae089",
             "d65a312d63ca317a"])

    def test_windows_ico_is_multi_resolution_and_shared_with_favicon(self):
        icon = (ROOT / "assets/madar.ico").read_bytes()
        self.assertEqual(icon, (ROOT / "public/favicon.ico").read_bytes())
        with Image.open(ROOT / "assets/madar.ico") as picture:
            self.assertGreaterEqual(len(picture.info["sizes"]), 7)
            self.assertIn((256, 256), picture.info["sizes"])
            self.assertIn((16, 16), picture.info["sizes"])

    def test_web_png_sizes_and_transparent_corners(self):
        for name, expected in (
            ("madar-icon-1024.png", 1024), ("madar-icon-512.png", 512),
            ("favicon-32.png", 32), ("apple-touch-icon.png", 180)
        ):
            with self.subTest(name=name), Image.open(ROOT / "public" / name) as img:
                self.assertEqual(img.size, (expected, expected))
                self.assertEqual(img.convert("RGBA").getpixel((0, 0))[3], 0)


if __name__ == "__main__":
    unittest.main()
