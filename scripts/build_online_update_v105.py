"""Immutable, QA-first 1.0.5 Windows build with installer-data backup gate."""
import build_p0_release_candidate as builder

builder.VERSION = "1.0.5"
builder.LABEL = "20261102-OnlineUpdate"
builder.PROGRAM = builder.RELEASE / "Madar-Desk-v1.0.5-OnlineUpdate.exe"
builder.QA = builder.RELEASE / "Madar-Desk-1.0.5-Setup-QA.exe"
builder.PROD = builder.RELEASE / "Madar-Desk-1.0.5-Setup.exe"
builder.QA_ROOT = builder.ROOT / ".qa-inno-v105-online-update"

if __name__ == "__main__":
    builder.main()
