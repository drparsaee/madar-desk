# Madar 1.0.4 Installer Preflight Fix2 (2026-11-02)

## Root cause and evidence

The owner attempted to upgrade from an existing 1.0.2 installation using
Madar-Desk-1.0.4-Setup.exe. Inno stopped during PrepareToInstall with the
generic message that Madar was running or its profile was unsafe.

Direct process enumeration during the failure showed two processes:
Madar-Desk-1.0.4-Setup and Madar-Desk-1.0.4-Setup.tmp.
The PowerShell preflight script used ProcessName -like Madar-Desk* and
therefore rejected the installer and Inno child **as if they were real
database writers**. The installation log confirmed the early preflight
failure. No binary activation took place; previously installed 1.0.2 was
still selected.

The process predicate now excludes only versioned Inno installer names
Madar-Desk-X.Y.Z-Setup and matching optional suffixes/temp variants.
Actual Madar-Desk, Madar-Desk-live, versioned executable and MadarHost
still block upgrades. The verified backup and fail-closed checks remain
mandatory. No live application process is killed.

## Test evidence

- Python PowerShell preflight tests: 12/12 passed, including new tests
  with both installer and child active, and negative tests proving
  active real application and LAN host still block installation.
- The new QA *Inno installer* (named to match the once-failing pattern)
  successfully installed an upgrade into a dedicated synthetic profile;
  verified pre-upgrade ZIP preserved all 3 files, prior EXE remained,
  rollback and forward activation passed.
- Separate fresh-install QA Inno installer succeeded with no seeded tasks.
- With no real Madar writer running, the corrected preflight was executed
  against the owner's real Roaming/MadarDesk profile. It exited zero,
  made a verified ZIP in the existing
  Local/MadarDesk-ReleaseBackups directory, and did not activate/change
  the installed app. This is a preflight validation, **not** a claim of
  successful real machine installation.

## Immutable source/program and new installer

- Application binary reused, unchanged:
  release/Madar-Desk-v1.0.4-RC-20261102-Logo1.exe
  SHA256 6963ad4440e56f0a662c670aa84cb626c7c22be9b135b0a05c34916c65635c60.
- Patched production installer:
  release/Madar-Desk-1.0.4-Setup-Fix2.exe
  SHA256 58b20bbfa9965f281532693b093049aeb5b0ab021d389749a4b062cfbb5c9d21.
- New delivery ZIP:
  D:/CoS-Test/Madar-Desk-1.0.4-Fix2-Ready.zip
  SHA256 ed41f195eabf1f07b88a19dfebb30768751ffbf24b1ca747666bcf495526fc8a.
- ZIP has precisely one EXE, with an independently verified uncompressed
  payload hash identical to the fixed production installer. Previous
  delivery ZIP and its one-file delivery folder were removed only after
  exact known old SHA validation. The original source release artifacts
  in release/ and user data are retained.
- Installer is still unsigned; user execution/SmartScreen remains
  unverified. This is an RC update installer, not proof of final deployment.
