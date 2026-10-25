# Madar Desk RC8 Rule Safety Candidate — Verification

**Build and verification:** 2026-10-21  
**Classification:** isolated Windows EXE candidate; not Stable, installed, deployed or migrated.

## Artifact

- Path: `release/Madar-Desk-v1.0-rc8-rule-safety-candidate.exe`
- Verified size: **13,854,878 bytes**
- Verified SHA-256: `9D063DF504BBC422F9CD8B6F6D07DA125B9228CA98B14DD9C47FCF39E79A62A0`
- Package metadata: `1.0.0-rc.8` in both package.json and package-lock.json.
- Guard `scripts/ensure_new_release.py` ran successfully before building; RC1–RC7 EXEs retained under distinct names.
- `npm run dist:rc`: exit **0**; PyInstaller one-file Windows EXE build log `.qa-rc8-build.log`.

## Fresh isolated full QA before RC8 build

`py -3.12 scripts/release_qa.py --full`, exit **0**:

| Group | Result | Evidence |
|---|---:|---|
| Release regressions | **19/19 PASS** | `.qa-full-post-m07.log` |
| Python full suite | **666/666 PASS** | same |
| JavaScript full suite | **265/265 PASS** | same |
| Combined counts (three invocations) | **950 pass** | no failed test reported |

The runner sets disposable `APPDATA` and `LOCALAPPDATA` in child test processes. This is not evidence that a real customer's data can be migrated or restored without any loss.

## Fresh EXE smoke

Command: `py -3.12 scripts/v1_gui_smoke.py --exe release/Madar-Desk-v1.0-rc8-rule-safety-candidate.exe --timeout 90 --screenshot --output-dir .qa-rc8-gui`

- Exit code **0**, smoke status **PASS**. Nine checked surfaces: localhost loopback, complete DOM, React root mount, readable Persian body, native/pywebview bridge, loaded font, five columns, four cards and screenshot artifact.
- Screenshot was parsed and PNG CRC/zlib-verified: **1484 × 921**, **142,308 bytes**.
- The native screenshot callback field reported `done:false`; the harness still accepted the complete verified PNG. This must not be rewritten as native callback success.
- Evidence: `.qa-rc8-gui-smoke.log`, `.qa-rc8-gui/v1-gui-smoke-868s_u5k/diagnostics.json`, and adjacent `screenshot.png`.

## M07 scope in RC8

- `m07_host_guard.py` delegates to `rule_safety.py` for bounded dry-run before enqueue and due-job preflight before execution.
- Source `native_app.py` uses the guard in optional unified SQLite automation paths under existing host locking and CAS. Limits: **25 events** per checked batch, **3 attempts** per job.
- Focused M07 proof includes `tests/test_m07_guard_unit.py` (**3/3**) and `tests/test_m07_host_preflight.py` (**9/9**) with disposable five-domain SQLite. Tests cover denied batches, accounting-domain preservation, authorization, deterministic order and unchanged revision on denial.
- This does **not** attest to signed persistent M07 audit or cross-restart causal ancestry, which have not been wired. Legacy JSON rule dispatch is not equivalent to the guarded SQLite engine path.

## Remaining manual/release gates

No verified acceptance on two physical Windows clients, 25 network edits under actual disconnect/reconnect, click-through Finance/Rules/AI GUI, multi-card drag/keyboard/focus, stable 1k/5k FPS on target hardware, full reference restore (tasks/GL/accounts/attachments/audit), production Drive connectivity, or five-user usability study.

M08 independent GL kernel has not replaced the authoritative existing accounting engine; no dual posting is permitted. M10 AI change review is currently a bounded, pure approval/undo plan, not a host-connected mutator with persisted human consent, provenance, audit and budget ledger.

**Do not label RC8 Stable or Trello parity 100%. Do not deploy/migrate real data without independent acceptance and explicit final authorization.**
