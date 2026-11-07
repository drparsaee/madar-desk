# Madar P2 entry: source implementation and outstanding gates (2026-11-07)

**Status:** P2 feature work has started. This is not a P2 completion, signed release, production deployment or approval of unresolved P1 release failures.

## Baseline and isolated branch

- The official installed Windows release remains **1.0.23**, and its original Git baseline is `22dbf1e`.
- P2 working tree: `D:\CoS-Test\000- Madar\madar-p2-gantt-notifications-20261107`, branch `feat/madar-p2-gantt-notifications-20261107`, created from Native P1 HEAD `0b6abb9`.
- The immutable 1.0.24 P0 candidate and the Web P1 integration worktree were **not** merged, installed, rebuilt, pushed or deployed.
- Taraz remains the independent finance application. No billing, membership tier, real online account provider or checkout is claimed active.

## Completed P2 slice

1. **Gantt dependency schedule diagnostics**, commit `d95bb0e`:
   - Highlight cards whose plan starts before or on the last planned day of a visible predecessor.
   - Distinguish unknown predecessor dates and references outside the authorized/current visible task view from verified non-conflicts.
   - Offer an explicit **one-card-only** date adjustment that preserves planned duration, when all predecessors used for the suggestion are visible and dated. This does not reschedule dependent successors or change due dates implicitly.
   - Display the warning in text and accessible control labels, not by color alone.
2. **Notifications and mention navigation**, commit `63f4032`:
   - Link an existing backend-authorized notification to its card or project conversation.
   - Resolve only against authenticated visible project, board, workspace and card snapshot, then revalidate current backend read permission before navigation. Denial shows a generic message without revealing hidden item IDs.
   - Explicit read acknowledgment with idempotent retry event IDs, unread counter, accessible error/status, keyboard focus handling, mobile dialog layout.
   - Existing `@username` parsing, durable notification data and role enforcement are reused; no parallel permission backend created.

## Executed verification

| Check | Observed outcome | Limits |
| --- | --- | --- |
| `npm.cmd run build` | PASS, Vite transformed 1692 modules | Source bundle only; main JS over 500 kB warning |
| Focused Node command (`gantt_model`, `gantt_view_persistence`, `gantt_p2_browser`, `p2_notifications`, `taskops`, `madar_settings_sections`) | **26/26 PASS, 0 skipped** | Synthetic Chromium and source tests, no installed executable |
| `py -3.12 -B tools/p1_task_only_gate.py` | **7/7 modules, 65 tests PASS**, no timeouts | Explicit task-only subset, not full Python release suite |
| P2 browser tests | Gantt interaction at widths 320/375/768; notification dialog synthetic browser at 480/1440 | No physical phones or two-PC TLS LAN |

## Next P2 work, in priority order

1. **P2-A advanced scheduling:** expand to explicit dependency-path analysis, inspect predecessor/successor side effects of rescheduling, include safe bulk move preview only after graph validation and role authorization.
2. **P2-B teamwork:** add eligible-user mention suggestions and unread notification cues, test revoked privileges, inaccessible references, two-client conflict/retry and real LAN scenarios.
3. **P2-C web parity:** merge reviewed, scoped P2 source changes into a new Web P2 branch based on the current Web P1 integration. Preserve its PWA/API/offline work and rerun full web/Chromium suites. No direct overwrite of the Web P1 worktree.
4. **P2-D online identity and subscription:** require a real identity service, product/pricing contract, payment provider/server webhooks and consent/security plan before enabling signup/payment; no simulated paid subscription or working checkout without an actual backend.

## Release gates remain red

- Prior full native legacy Python sweep: 204 modules executed, 174 passing, **30 failing**, identities of 26 current failures unavailable. Four historical baseline-matched modules were mixed/legacy finance; this is not permission to ignore all current failures.
- Physical multi-device LAN with actual TLS, production-host browser and offline recovery, Windows signed installer, real profile migration, rollback drill and Web P2 parity remain unchecked.
- Do not repurpose or overwrite the existing `1.0.24` P0 candidate as the P2 artifact. A future candidate needs a distinct version and its own packaging evidence.
