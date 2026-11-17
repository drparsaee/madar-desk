# E2 local two-hop host-to-peer verification (2026-11-10)

**Disposition: synthetic source pilot PASSED its scoped tests; official financial delivery NOT accepted.** This note records a fresh verification, not a production deployment or a financial event.

## Source and boundaries

- Madar isolated worktree `D:\CoS-Test\000- Madar\madar-p2-gantt-notifications-20261107` (observed HEAD `32bd8ff`, dirty).
- Taraz detached worktree `D:\CoS-Test\000- Taraz\taraz-mtr-e2-isolated-20261109` (observed HEAD `653089b`, dirty).
- Madar `mtr_e2_host_peer_pilot.py`, `mtr_e2_dispatch_gate.py`, `mtr_lan_finance_adapter.py`, `mtr_peer_https_pilot.py` and their synthetic tests; Taraz `taraz_mtr_catalog_read.py`, `tests/test_taraz_mtr_catalog_read.py`.
- No installed Windows service, live company book, real user, financial transaction, official document or second physical PC was used. This execution did not commit, push, deploy, install or change network/firewall/printer/file-share configuration.

## Commands and results observed in this continuation

From the detached **Taraz** worktree:

```powershell
$env:PYTHONIOENCODING='utf-8'
py -3.12 -B -m unittest -v tests.test_taraz_mtr_catalog_read
exit $LASTEXITCODE
```

**25 tests, OK, exit 0, 37.267 seconds.** Synthetic company registry, local identity, SQLite store and catalog field/row grants were exercised. This proves bounded safe projection for the tested local fixtures only, not authenticity of imported parties or an official remote catalog API.

From isolated **Madar** with `MTR_TARAZ_SOURCE` pointing exclusively at the detached synthetic Taraz worktree:

```powershell
$env:MTR_TARAZ_SOURCE='D:\CoS-Test\000- Taraz\taraz-mtr-e2-isolated-20261109'
$env:PYTHONIOENCODING='utf-8'
py -3.12 -B -m unittest -q tests.test_mtr_e2_host_peer_pilot tests.test_mtr_e2_dispatch_gate tests.test_mtr_lan_finance_adapter tests.test_mtr_peer_https_pilot
$code=$LASTEXITCODE
Remove-Item Env:MTR_TARAZ_SOURCE
exit $code
```

**46 tests, OK, exit 0, 48.149 seconds.** The included host-peer subset is **11 tests, including 5 inherited cross-source tests**, and was separately reported as 11/11 OK in the preceding continuation. Do not count that subset as 11 new distinct scenarios on top of this run. The current command completed with exit 0 and removed the temporary source environment variable.

## What this does NOT prove

1. The peer registry records signed **metadata arrival**, **not** an official Taraz finance receipt, approval, party link, invoice, tax document or ledger posting.
2. A durable SQLite dispatch slot enforces **at most one attempted send**, not a transactional exactly-once official finance event across Madar outbox, dispatch gate, network and Taraz ledger. After a lost ACK, status remains unknown until a signed query. Never assume nonreceipt and never auto-resend.
3. Test TLS pins and tokens are disposable synthetic fixtures; no separate production Taraz peer identity or permission-scoped real remote API has been validated.
4. The Taraz catalog reader validates a local active session and local company book, but additional project/row/field ACL rules are trusted host-operator-injected policy. They are not independently derivable from a native Taraz remote authority in this pilot.
5. No physical two-PC test, power-loss recovery, independent ledger idempotency, operational backup/readback/restore or installed-client UX acceptance was performed.

**E7 remains OPEN:** in particular AC-05, AC-07, AC-12, AC-13, G-03, G-06 and G-08 cannot close on these synthetic results.
