"""Build immutable, cumulative Madar Desk 1.0.8 release artifacts."""
import build_p0_release_candidate as builder

builder.VERSION = "1.0.8"
builder.LABEL = "20261103-CardCover"
builder.PROGRAM = builder.RELEASE / "Madar-Desk-v1.0.8-CardCover-20261103.exe"
builder.QA = builder.RELEASE / "Madar-Desk-1.0.8-Setup-CardCover-QA.exe"
builder.PROD = builder.RELEASE / "Madar-Desk-1.0.8-Setup-CardCover.exe"
builder.QA_ROOT = builder.ROOT / ".qa-inno-v108-cardcover"

if __name__ == "__main__":
    builder.main()
