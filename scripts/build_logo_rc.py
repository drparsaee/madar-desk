"""Build an immutable 1.0.4 RC with the user-supplied Madar brand assets.

The preceding 1.0.3 RC stays untouched. This imports the existing audited
PyInstaller and Inno Setup builder and changes only the output identity.
Requires an existing Microsoft-signed offline WebView2 prerequisite.
"""

from pathlib import Path
import build_p0_release_candidate as build

build.VERSION = "1.0.4"
build.LABEL = "20261102-Logo1"
build.PROGRAM = build.RELEASE / f"Madar-Desk-v{build.VERSION}-RC-{build.LABEL}.exe"
build.QA = build.RELEASE / f"Madar-Setup-v{build.VERSION}-RC-{build.LABEL}-QA.exe"
build.PROD = build.RELEASE / f"Madar-Setup-v{build.VERSION}-RC-{build.LABEL}.exe"
build.QA_ROOT = build.ROOT / ".qa-inno-v104-logo1-20261102"


if __name__ == "__main__":
    build.main()
