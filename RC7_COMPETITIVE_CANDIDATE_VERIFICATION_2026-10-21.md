# Madar Desk RC7 Competitive Candidate — Verification

**Date:** 2026-10-21  
**Kind:** isolated Windows executable candidate, NOT Stable/production  
**Artifact:** `release/Madar-Desk-v1.0-rc7-competitive-candidate.exe`

## Artifact identity

- Size: **13,840,449 bytes**
- SHA-256: `E655D2824A8F9B7DEA8D7FE072DB54025306234FE5392B985ADA241B1118A1D9`
- File timestamp observed (UTC): `2026-10-21T13:23:25`
- Package version at verification: `1.0.0-rc.7`
- Build: PyInstaller `--onefile --windowed`, release guard `scripts/ensure_new_release.py` blocked name reuse; RC1–RC6 kept.

## Isolated automated QA (source before candidate build)

- `py -3.12 scripts/release_qa.py --full` **EXIT 0**
- Release regression: **19/19 PASS**, 17.700s
- Full Python: **632/632 PASS**, 262.934s
- JavaScript: **265/265 PASS**
- Full suite uses disposable `APPDATA` and `LOCALAPPDATA`; this does not validate production/user data.
- A subsequent standalone test `py -3.12 -m unittest tests.test_m02_reconnect_25_edits -v`: **2/2 PASS** with 25 synthetic nonoverlapping changes, plus explicit same-card conflict retention. This test was added after the RC7 build. It is not evidence for physical two-computer acceptance.

## Isolated Windows EXE smoke

- `py -3.12 scripts/v1_gui_smoke.py --exe release/Madar-Desk-v1.0-rc7-competitive-candidate.exe --timeout 90 --screenshot --output-dir .qa-rc7-gui` **EXIT 0**
- Smoke report has **9 PASS** observations: localhost server, document readiness, React root, Persian body text, native JS bridge, font, 5 board columns, 4 cards, screenshot.
- Verified screenshot: **1484 × 921 PNG**, **142,468 bytes**; report notes `native_done:false` even though PNG CRC and zlib stream passed verification.
- Screenshot/report evidence: `.qa-rc7-gui/v1-gui-smoke-8h_vjwkk/`.

## Scope and blockers

No claim of 100% Trello public-feature parity, Stable release, full interactive test, real Windows two-PC LAN, real Google Drive, live finance recovery or human usability acceptance is made.

- M-03 real FPS and interaction under 1k/5k cards not measured.
- M-04 5-user usability not measured.
- M-06 Today/Waiting/calendar dependency integration and due-date warnings incomplete.
- M-07 safety preflight isolated, not CAS-wired to production automation dispatch.
- M-08 independent new GL kernel is not the authoritative same-store ledger; existing accounting core remains the host path. Never dual-post.
- M-09 operational export deliberately omits financial journals, attachments' binary bytes, users, comments, and provenance. Not a full backup.
- M-10 AI proposal approval/provenance worker implementation is independent of this EXE unless explicitly host-wired and rebuilt.
- Full source after candidate creation may contain new test/module files; a PASS does not automatically extend to later changes. No deployment or live data migration authorized.
