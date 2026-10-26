"""Bundle audited OFL licenses and Vazirmatn fallback for Madar's offline UI.

Vite bundles Estedad's variable font files through its Fontsource CSS import;
this step retains the respective OFL texts and the Vazirmatn fallback.
"""
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
source = root / "node_modules" / "vazirmatn"
font = source / "fonts" / "webfonts" / "Vazirmatn[wght].woff2"
license_file = source / "OFL.txt"
if not font.is_file() or not license_file.is_file():
    raise SystemExit("Vazirmatn npm package missing. Run npm install first.")

estedad = root / "node_modules" / "@fontsource-variable" / "estedad"
estedad_license = estedad / "LICENSE"
estedad_css = estedad / "wght.css"
estedad_files = estedad / "files"
needed_subsets = ("arabic", "latin", "latin-ext", "vietnamese")
if not estedad_license.is_file() or not estedad_css.is_file() or any(
    not (estedad_files / f"estedad-{name}-wght-normal.woff2").is_file()
    for name in needed_subsets
):
    raise SystemExit("Estedad OFL package is missing or incomplete. Run npm install first.")
if ("SIL Open Font License" not in estedad_license.read_text(encoding="utf-8")
        or "SIL Open Font License" not in license_file.read_text(encoding="utf-8")):
    raise SystemExit("Cannot verify required OFL license texts for bundled fonts.")

destination = root / "public" / "fonts"
destination.mkdir(parents=True, exist_ok=True)
shutil.copyfile(font, destination / "Vazirmatn.woff2")
shutil.copyfile(license_file, destination / "OFL.txt")
shutil.copyfile(estedad_license, destination / "Estedad-OFL.txt")
print("Bundled offline Estedad OFL notice and Vazirmatn fallback into UI.")
