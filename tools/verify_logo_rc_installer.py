"""Actual QA Inno installation, upgrade/rollback and clean-install for 1.0.4."""

from pathlib import Path
import p0_installer_acceptance as upgrade
import p0_fresh_installer_acceptance as fresh

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "release"
VER = "1.0.4"
STAMP = "20261102-Logo1"

upgrade.VER = VER
upgrade.LABEL = STAMP
upgrade.PROGRAM = RELEASE / f"Madar-Desk-v{VER}-RC-{STAMP}.exe"
upgrade.QA = RELEASE / f"Madar-Setup-v{VER}-RC-{STAMP}-QA.exe"
upgrade.QA_ROOT = ROOT / ".qa-inno-v104-logo1-20261102"

fresh.VERSION = VER
fresh.STAMP = STAMP
fresh.PROGRAM = upgrade.PROGRAM
fresh.FRESH = RELEASE / f"Madar-Setup-v{VER}-RC-{STAMP}-QA-Fresh.exe"
fresh.FRESH_ROOT = ROOT / ".qa-inno-v104-logo1-20261102-fresh"


if __name__ == "__main__":
    upgrade.main()
    fresh.main()
    print("BRANDED_RC_INSTALL_ACCEPTANCE_PASS", flush=True)
