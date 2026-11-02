"""Verify the exact 1.0.8 Inno setup against two isolated test profiles."""
from pathlib import Path
import p0_installer_acceptance as upgrade
import p0_fresh_installer_acceptance as fresh

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "release"
VER = "1.0.8"
LABEL = "CardCover-20261103"

upgrade.VER = VER
upgrade.LABEL = LABEL
upgrade.PROGRAM = RELEASE / f"Madar-Desk-v{VER}-{LABEL}.exe"
upgrade.QA = RELEASE / f"Madar-Desk-{VER}-Setup-CardCover-QA.exe"
upgrade.QA_ROOT = ROOT / ".qa-inno-v108-cardcover"

fresh.VERSION = VER
fresh.STAMP = LABEL
fresh.PROGRAM = upgrade.PROGRAM
fresh.FRESH = RELEASE / f"Madar-Desk-{VER}-Setup-CardCover-QA-Fresh.exe"
fresh.FRESH_ROOT = ROOT / ".qa-inno-v108-cardcover-fresh"

if __name__ == "__main__":
    upgrade.main()
    fresh.main()
    print("INTEGRATED_108_INSTALL_ACCEPTANCE_PASS", flush=True)
