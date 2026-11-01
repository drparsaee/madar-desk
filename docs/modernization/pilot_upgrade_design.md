# Pilot: versioned installer safety | Design

## Target module

**Keep the existing Windows PowerShell + Inno Setup architecture.** This pilot is a bounded uplift of the input validation in `Madar-Upgrade-Preflight.ps1`; it does not introduce services, databases, new APIs, or a new installer version.

## Target contract and data model

- Inputs remain the three named command-line arguments `-DataRoot`, `-BackupRoot` and `-TargetVersion`.
- A valid root is an absolute Windows path beneath a drive volume (for example `C:\Users\...\MadarDesk`), **not** the drive root `C:\`.
- Preserve existing checks for paths overlapping, junctions/reparse points, running Madar processes and snapshot integrity.
- Outputs remain the existing `FRESH_PROFILE:` / `BACKUP_VERIFIED:` messages, verified ZIP or a non-zero failure.
- The zip contents and original profile bytes for a valid path must match the old implementation. No storage schema or activation pointer may change because of this pilot.

## Design decision

Resolve `GetFullPath` first and reject paths exactly equal to `GetPathRoot` with case-insensitive comparison **before** `TrimEnd('\')`. This also catches paths normalized back to a volume root with `..`.

## No HTTP API

The Cookbook's OpenAPI step does not apply to this pilot because its public boundary is a PowerShell command and an Inno Setup hook, not an HTTP service. See `pilot_upgrade_contract.yaml` for a machine-readable CLI interface contract. Creating a fictional REST API would make the design less accurate.
