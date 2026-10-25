# Madar Desk: independent accounting engine investigation (2026-10-21)

**Status:** research + isolated prototype only. Not merged into Native host, LAN, React or SQLite bundles. This file is for Prime/parallel-worker coordination. Do **not** treat as a released feature.

## Local artifacts

- REA installed earlier: `D:\CoS-Test\rea-lab\cli\node_modules\rea-agents\scripts\rea.mjs` (npm `rea-agents@6.7.0`), Codex MCP/skill registration previously verified.
- Accounting source reference: `D:\CoS-Test\rea-lab\erpnext-source`, pinned commit `05a43eb40fee1da5599004869e6d76c1ad6e8442`.
- Annotated code paths, gap matrix, posting rules: `D:\CoS-Test\rea-lab\ACCOUNTING_REFERENCE_ANALYSIS.md`.
- Isolated SQLite prototype: `D:\CoS-Test\rea-lab\accounting-prototype\ledger_core.py`, **14/14 disposable tests passed** via Python 3.12.10. This is not integrated, audited or deployable production accounting.
- Ghidra 12.1.4 and Temurin 21 are pinned with hashes; **not installed** because official archive downloads were too slow to complete in this execution. Do not call REA native Ghidra analysis verified.
- A further 12:37 local-time retry tried official GitHub, a GitHub transport mirror, Microsoft winget and Azul CDN. Official/mirror 1 MiB Ghidra bytes matched; large verified archive download still failed to complete. `rea-lab/ACCOUNTING_REA_HANDOFF.md` has observed timings and diagnostic scope.
- Independent `.NET` PE smoke test **passed** with REA's execution-free managed analyzer (`rea-lab/managed-fixture/{artifact,members}.json`), exposing sample members `Subtotal` and `Balanced`. This is not a substitute for Ghidra native provider and does not integrate accounting into Madar.

## Read-only observations of existing Madar

The current `finance.py` records internal invoice contracts/issuance/payments and card costs, with exact amounts and event idempotency, but **no general double-entry GL** in the inspected code. `app_storage.py` stores existing domains transactionally in an opt-in revisioned SQLite bundle; it must be coordinated before introducing journal persistence. Documentation: `FINANCE_DOMAIN.md`.

## Recommended next integration phase (needs file ownership coordination)

1. Freeze current interface and read `finance.py`, `app_storage.py`, Native Bridge and user ACL status; choose one authoritative transaction.
2. Draft `chart_of_accounts`, `fiscal_period`, `posted_journal` and `journal_line` shapes, with company separation, immutable data, fiscal closure and explicit minor currency units.
3. Connect issued invoice, **proven** receipts, vendor bills, advances and reversals via durable outbox; map each event to balanced GL rows. Drafts do not post.
4. Integrate all state changes under a single atomic commit, durable idempotency, current authorization and failure-recovery tests. Never bolt on another independent SQLite database as a second writer.
5. Prove isolated, bridge and desktop tests separately; ensure viewer finance redaction, two-client concurrency and backup/restore. Local prototype tests are not evidence of full Madar integration.

## Caveats

- ERPNext source is GPL-3.0; architecture was studied, **no GPL code copied** to the isolated prototype.
- AccountEdge Pro terms limit reverse engineering; no commercial EXE was acquired or decompiled. Its public UX/docs can inform independent requirements only.
- No Iranian tax/samaneh modian compliance has been checked or implemented.
- No APPDATA data was used; the active code modules in Madar were not edited by this investigation.
