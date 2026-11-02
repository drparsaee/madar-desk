"""Derive all Windows and web icon sizes from the exact rendered master SVG."""

from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "assets" / "madar-logo-rgba-1024.png"
PUBLIC = ROOT / "public"
ASSETS = ROOT / "assets"
SIZES = ((16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
         (128, 128), (256, 256))


def main():
    with Image.open(RAW) as source:
        icon = source.convert("RGBA")
    if icon.size != (1024, 1024):
        raise RuntimeError("Renderer must produce a 1024x1024 source")
    if icon.getpixel((0, 0))[3] != 0:
        raise RuntimeError("Brand icon lost the transparent rounded corners")
    if icon.getpixel((512, 512))[3] != 255:
        raise RuntimeError("Brand icon interior is unexpectedly transparent")
    icon.save(PUBLIC / "madar-icon-1024.png", optimize=True)
    icon.resize((512, 512), Image.Resampling.LANCZOS).save(
        PUBLIC / "madar-icon-512.png", optimize=True)
    icon.resize((180, 180), Image.Resampling.LANCZOS).save(
        PUBLIC / "apple-touch-icon.png", optimize=True)
    icon.resize((32, 32), Image.Resampling.LANCZOS).save(
        PUBLIC / "favicon-32.png", optimize=True)
    icon.save(ASSETS / "madar.ico", format="ICO", sizes=SIZES)
    (PUBLIC / "favicon.ico").write_bytes((ASSETS / "madar.ico").read_bytes())
    with Image.open(ASSETS / "madar.ico") as generated:
        observed = generated.info.get("sizes", set())
    if not {(16, 16), (32, 32), (48, 48), (256, 256)}.issubset(observed):
        raise RuntimeError("Multi-resolution Windows ICO export incomplete")
    RAW.unlink()
    print("BRAND_ICONS_READY", sorted(observed))


if __name__ == "__main__":
    main()
