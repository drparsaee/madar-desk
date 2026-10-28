"""Produce Windows and browser icons from the owner-approved vector mark.

Requires Pillow and an existing Playwright/Chromium installation. Run once from
the repository root with: python scripts/build_madar_brand.py
"""
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
ASSETS = ROOT / "assets"


def main():
    ET.parse(ASSETS / "madar-final.svg")
    PUBLIC.mkdir(exist_ok=True)
    shutil.copyfile(ASSETS / "madar-final.svg", PUBLIC / "madar-icon.svg")
    subprocess.run(["node", str(ROOT / "scripts" / "render_madar_brand.cjs")], cwd=ROOT, check=True)
    with Image.open(PUBLIC / "madar-icon-1024.png") as raw:
        artwork = raw.convert("RGBA")
        artwork.resize((512,512), Image.Resampling.LANCZOS).save(PUBLIC / "madar-icon-512.png")
        artwork.resize((180,180), Image.Resampling.LANCZOS).save(PUBLIC / "apple-touch-icon.png")
        artwork.resize((32,32), Image.Resampling.LANCZOS).save(PUBLIC / "favicon-32.png")
        sizes = [(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)]
        artwork.save(ASSETS / "madar.ico", format="ICO", sizes=sizes)
        artwork.save(PUBLIC / "favicon.ico", format="ICO", sizes=sizes)
    print("Madar final logo: SVG, PNG and Windows/browser ICO generated")


if __name__ == "__main__":
    main()
