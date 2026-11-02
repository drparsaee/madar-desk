"""Exercise real Inno 1.0.7 installer only against disposable QA profiles."""
from pathlib import Path
import p0_installer_acceptance as upgrade
import p0_fresh_installer_acceptance as fresh

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "release"
VER = "1.0.7"
LABEL = "Integrated-Fix1-20261102"

upgrade.VER = VER
upgrade.LABEL = LABEL
upgrade.PROGRAM = RELEASE / f"Madar-Desk-v{VER}-{LABEL}.exe"
upgrade.QA = RELEASE / f"Madar-Desk-{VER}-Integrated-Fix1-Setup-QA.exe"
upgrade.QA_ROOT = ROOT / ".qa-inno-v107-integrated-fix1"

fresh.VERSION = VER
fresh.STAMP = LABEL
fresh.PROGRAM = upgrade.PROGRAM
fresh.FRESH = RELEASE / f"Madar-Desk-{VER}-Integrated-Fix1-Setup-QA-Fresh.exe"
fresh.FRESH_ROOT = ROOT / ".qa-inno-v107-integrated-fix1-fresh"

if __name__ == "__main__":
    upgrade.main()
    fresh.main()
    print("INTEGRATED_107_INSTALL_ACCEPTANCE_PASS", flush=True)
