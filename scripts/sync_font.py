"""Copy official OFL Vazirmatn assets from npm to the packaged UI."""
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
source = root / "node_modules" / "vazirmatn"
font = source / "fonts" / "webfonts" / "Vazirmatn[wght].woff2"
license_file = source / "OFL.txt"
if not font.is_file() or not license_file.is_file():
    raise SystemExit("Vazirmatn npm package missing. Run npm install first.")
destination = root / "public" / "fonts"
destination.mkdir(parents=True, exist_ok=True)
shutil.copyfile(font, destination / "Vazirmatn.woff2")
shutil.copyfile(license_file, destination / "OFL.txt")
print("Bundled Vazirmatn OFL assets into UI.")
