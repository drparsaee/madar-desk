# Madar Desk 1.0.4 RC Logo1 | Branding change and acceptance

## User-authorized scope

Replace supplied Madar Logo-06.svg in the application UI, native Windows
executable icon (including shortcuts/taskbar), and Inno Setup installer.
Do not replace company invoice logos, profile photos, accounting identities,
or any end-user data. Keep the 1.0.3 RC binary immutable.

## Graphic evidence

- The user's Illustrator SVG had two large, nonrendered Adobe metadata records.
  Removed those only. Five visible SVG path SHA-256 prefixes match original:
  117cd8a9e0c733f8, ed345336720e59d4, c48ce0eb51393311,
  e5bc5c54c45ae089, d65a312d63ca317a.
- Original fills, shadow, dark gradient, 340.16 viewBox and 42.52 corner radius
  are retained. Asset and public master SVGs are byte-identical.
- scripts/render_madar_brand.mjs uses an isolated local headless Chrome profile
  for transparent PNG rasterization. scripts/sync_madar_brand_icons.py exports
  1024/512/180/32 px PNGs and 7-size Windows ICO (16 through 256 px).
- PyInstaller and Inno Setup both consume assets/madar.ico. Extracted icons
  from the built EXE and Setup are each pixel-identical to new favicon-32.png
  at 32x32 RGBA (mean absolute channel difference = 0).

## Immutable release identity and tested installer

- New version: 1.0.4, release label 20261102-Logo1.
- EXE: release/Madar-Desk-v1.0.4-RC-20261102-Logo1.exe
  SHA-256 6963ad4440e56f0a662c670aa84cb626c7c22be9b135b0a05c34916c65635c60.
- Installer: release/Madar-Setup-v1.0.4-RC-20261102-Logo1.exe
  SHA-256 3995bc5de5619efebae5c2d00ce2d43d3e5b40b8da16049864bdc4f6233ece68.
- Previous installer 1.0.3 still has SHA-256
  a838e8ada4b8ce402ad9835421c23020704aa09efd0e24450c80d2f175af30f3.
- Actual Inno QA upgrade exited 0. A verified ZIP preserved three synthetic
  profile files byte-for-byte; old binary preserved; rollback and reactivation
  succeeded. Separate fresh-install QA also exited 0 with no seeded tasks.
- The new installer is NotSigned. No actual customer installation or real
  profile, hardware power loss, SmartScreen, accounting, Parsian or physical
  LAN acceptance was attempted.

## Source validation and delivery gates

The brand test module passed 3/3 tests. Initial official npm test invocation
reported **172 of 173 Python modules** passing with 1 unexpected error. The
isolated QA directory was removed on launcher exit, so the failing module's
diagnostic was not retained; its exact cause was **not established**. Focused
upgrade, isolated-runner and brand modules then passed 18/18. A fresh
whole-project per-module isolated Python rerun (logged to a temporary JSON
report outside the repo) passed **173/173 modules, 1,655 tests reported,
2 skips, 2 expected failures, zero unexpected errors or failures, zero
timeouts**. Vite build passed and serial Node/React/Chromium tests passed
**530/530 with zero skips/failures**, exit 0.

These are successful independent component-suite reruns, **not** a claim that
the original failed npm test invocation itself was green. The original
isolated QA failure remains uncharacterized and could be transient.
Final source commit, LocalForge SHA readback and the ignored built release
artifact hashes are separate publication gates.
