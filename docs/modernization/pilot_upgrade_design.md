# Pilot: versioned installer safety | Design

## Target module

**Keep the existing Windows PowerShell + Inno Setup architecture.** Phase 2 extends the bounded path validation in `Madar-Upgrade-Preflight.ps1` and `Madar-Activate-Version.ps1`, and adds fail-closed ZIP publication. It does not introduce services, databases, new APIs, or a new installer version.

## Target contract and data model

- Inputs remain the three named command-line arguments `-DataRoot`, `-BackupRoot` and `-TargetVersion`.
- A valid root is an absolute Windows path beneath a drive volume (for example `C:\Users\...\MadarDesk`), **not** the drive root `C:\`.
- Preserve existing checks for paths overlapping, junctions/reparse points, running Madar processes and snapshot integrity.
- Outputs remain the existing `FRESH_PROFILE:` / `BACKUP_VERIFIED:` messages, verified ZIP or a non-zero failure.
- The zip contents and original profile bytes for a valid path must match the old implementation. No storage schema or activation pointer may change because of this pilot.

## Design decision

Resolve `GetFullPath` first and reject paths exactly equal to `GetPathRoot` with case-insensitive comparison **before** `TrimEnd('\')`. This also catches paths normalized back to a volume root with `..`.

For an existing profile, write the ZIP into a uniquely named `.partial` in the
backup directory. Index ZIP entries in an ordinal dictionary, reject duplicate
names, and compare each archived file's size and SHA-256 to its source. Rename
the fully verified partial to a unique final ZIP on the same volume, and clean
up incomplete partials in `finally`. The final ZIP name remains compatible
with existing `Madar-Before-<version>-*.zip` discovery.

Activation must reject `InstallRoot` equal to the volume root, including
normalization through `..`, before any target EXE/path lookup. Version-pointer
mutation still follows successful executable checksum verification only.

## No HTTP API

The Cookbook's OpenAPI step does not apply to this pilot because its public boundary is a PowerShell command and an Inno Setup hook, not an HTTP service. See `pilot_upgrade_contract.yaml` for a machine-readable CLI interface contract. Creating a fictional REST API would make the design less accurate.
