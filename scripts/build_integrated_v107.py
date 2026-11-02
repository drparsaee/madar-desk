"""Immutable integrated release candidate for local owner installation.

Source combines card/search/accounting integration and safe SMB/updater release.
The candidate must pass targeted/installer acceptance before activation.
"""
import build_p0_release_candidate as builder

builder.VERSION = "1.0.7"
builder.LABEL = "20261102-Integrated-Fix1"
builder.PROGRAM = builder.RELEASE / "Madar-Desk-v1.0.7-Integrated-Fix1-20261102.exe"
builder.QA = builder.RELEASE / "Madar-Desk-1.0.7-Integrated-Fix1-Setup-QA.exe"
builder.PROD = builder.RELEASE / "Madar-Desk-1.0.7-Integrated-Fix1-Setup.exe"
builder.QA_ROOT = builder.ROOT / ".qa-inno-v107-integrated-fix1"


if __name__ == "__main__":
    builder.main()
