# Madar Desk | Phase 3 modernization results and release gates

Date of work: 2026-11-01. Baseline: `60beedd589903949269464176416ae6bebf78fb7` on `modernization/phase2-20261101`. All work performed in the separate `D:\CoS-Test\madar-codex-modernization-phase2-20261101` worktree, not an installed app.

## Source changes with characterized evidence

| Boundary | Before | After | Verification |
|---|---|---|---|
| Version activation | Windows installation version dir could be a junction to a location outside install root, yet activate by hash | Reject reparse/junction paths through the target executable and pointer ancestry | Synthetic red-before/green-after test; upgrade/restore group 20/20 |
| Accounting manual backup publication | Directory sync failure after hard-link publish raised but left a backup at a name the caller considered failed | Revoke only the just-published hard-link when still owned by the temporary copy; preserve replacements | Red-before test, 2 new successful, backup/restore group 81/81 |
| LAN HTTP boundary | Signed Content-Length could reach login; absolute authority, normalized // path, missing HTTP/1.1 Host could route as local | Validate request target using original request line, Host and ASCII Content-Length before dispatch | Red-before raw HTTP tests, security/LAN group 83/83 |
| Portable installer output | PowerShell auto-formatted SHA-256 to two characters on a narrow console | Print exact `INSTALL_VERIFIED_SHA256` digest while retaining byte/hash verification | Red-before exact-marker test, host/installer suite 26 tests OK (1 skip) |
| Historical test parity | Older integration tests assumed sample cards auto-created for new customers, contradicting current empty-first-run decision | Add sample cards **only** in disposable fixtures, avoiding lifecycle receipts from test setup | From initial 136/167 passing modules to final 168/168 passing modules |
| Offline edit conflict test | Simulated an offline host returning but did not restore a mock authorized session; conflict algorithm was never invoked | Set a synthetic authenticated LAN connection before comparing concurrent edits | Offline/reconcile group 7/7; no production merge logic altered |

## Final executed suite (isolated fixtures)

- Python 3.12 source-level suite: **168/168 modules passed**, 1,601 tests reported, 2 skipped, 2 expected failures, **0 unexpected assertion failures, 0 errors, 0 timeouts**. Runner: `tools/modernization_python_suite.py`, artifacts `full_python_phase3_final.json`. Each Python module ran as a separate subprocess with disposable `APPDATA`, `LOCALAPPDATA`, `TEMP`, `HOME` and `USERPROFILE`.
- JavaScript / React: **530/530 tests passed**, no skip or fail; executed sequentially.
- Vite production bundle: `npm run build` succeeded. Existing Rollup advisory notes some JS chunks exceed 500kB; no claim of startup-performance optimization.
- PowerShell syntax parse: `Install-MadarDesk.ps1`, `Madar-Upgrade-Preflight.ps1` and `Madar-Activate-Version.ps1` each returned zero parse errors. Relevant Python compile and `git diff --check` passed.
- Historical audit runs and their failure counts remain independently recorded in `full_python_phase3_audit.md` and `full_python_phase3_results.json` instead of being rewritten to look green.

## Explicitly NOT verified / release blocked

1. Packaged `MadarHost.exe` acceptance: `test_packaged_madar_host_exe.py` requires an actual built executable, which was absent and intentionally excluded from the 168-module runner. A separate old RC installer EXE fixture was also missing (one optional skip).
2. Real user profile backup/restore with meaningful customer attachments and accounting identities **not executed**; the installed version remains **1.0.2** and user data is untouched.
3. Import/migration of an actual Parsian database, rial/toman migration, full trial-balance reconciliation and finance-owner approval remain outstanding.
4. Real two-machine TLS/LAN pairing, certificate handling, firewall and live permissions not accepted on actual hardware. Synthetics do not prove absence of all security defects.
5. Fresh signed installer, crash/power-failure durability, antivirus/SmartScreen and Windows end-to-end update/rollback acceptance remain outstanding. No installer may be deployed based solely on source-level regression.
6. This phase is a **bounded modernization of known trust boundaries plus regression stabilization**, not proof that every source line was refactored or that the entire accounting product is ready to release.

## Source delivery status

Commit, private branch push, SHA verification and installation are separate steps. Record actual commit SHA and whether LocalForge accepted the push only after executing each operation.
