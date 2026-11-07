# Madar P2: successor-impact preview before Gantt drag save

Date: 2026-11-07. **Local-source feature and regression QA only. Not a release or user-data migration.**

## Scope and isolation

- Native P2: `feat/madar-p2-gantt-notifications-20261107` (previous HEAD `a6f79ee`).
- Web P2: `feat/madar-p2-web-parity-20261107` (previous HEAD `b44d9bd`).
- The installed 1.0.23, original Web P1 branch, immutable 1.0.24 P0 candidate, Taraz and real operational profiles were not changed by this sprint.
- All date proposals are **calendar-day, finish-to-start, forward-only** simulations over the authorized, currently visible task set. They do not model weekends, holidays, resource limits or hidden successors.

## Delivered behavior

1. Pure `previewGanttShiftImpact(tasks, taskId, days)` in `src/gantt_model.js` validates complete known plans and project-local dependencies, then traverses a bounded DAG in topological order. It preserves each successor's original duration and free gap where possible, and predicts cascading forward shifts only when necessary.
2. Fails closed for outside-view predecessors, incomplete/invalid dates, duplicate edges, cycles, pre-existing schedule conflicts, out-of-range shifts or a proposed start before a predecessor finishes. No private predecessor IDs or titles are included in blocked responses.
3. Gantt drag now **stages a preview** instead of writing immediately. A per-row keyboard-accessible button provides the same preview without drag. The panel can explore earlier/later dates and reports proposed dates for up to eight visible dependent tasks plus the total count.
4. If any dependent task would need to move, there is **no bulk confirmation button**; that requires an atomic backend batch operation with ACL/CAS first. When no known visible successor needs rescheduling, a separate explicit confirmation invokes the existing one-card `onUpdate` path. Viewers cannot request or confirm edits.
5. The pre-existing per-card date inputs and one-card conflict-repair control retain their previous direct edit behavior. **This change does not claim to intercept every possible scheduling edit.**
6. The Web P2 browser fixture and drag integration test now verify no write on pointer drag, presence of dependent impact, and an explicit safe one-card confirmation after shifting earlier. Web P1's original test was not overwritten.

## Observed tests

| Environment | Command/scope | Observed result |
| --- | --- | --- |
| Native P2 | `node --test tests/gantt_model.test.cjs tests/gantt_p2_browser.test.cjs` | 15/15 PASS, no skips |
| Native P2 | `npm.cmd run build` and focused Gantt/mentions/notifications/taskops suites | Build PASS (1692 modules); 32/32 tests PASS, no skips |
| Native P2 | `py -3.12 -B tools/p1_task_only_gate.py` | 7 selected modules / 65 tests PASS |
| Web P2 | Full `npm.cmd run test:web` first run | 53/54 PASS: one `web_server_api` fixture failed before reaching HTTP due to Node fetch `bad port` |
| Web P2 | Port fixture exclusion + two focused retests | 2/2 PASS for that exact conversation-move test; test-only change, no API code edit |
| Web P2 | Repeat full `npm.cmd run test:web` | 54/54 PASS, no skips; Vite Web build 1700 modules PASS |
| Web P2 | Additional P2 Chromium/UI/taskops/settings tests | 20/20 PASS, no skips |

Both production Vite builds warned about JavaScript bundles over 500 kB. The Web P2 port-fixture change addresses a synthetic test harness edge case, not production network behavior.

## Still unverified / gated

- A production-grade **atomic batch reschedule** with current server-side ACL, revision/CAS checking, rollback and dependent-card visibility is not implemented. Do **not** auto-apply the preview's successor proposals.
- The preview cannot know successors outside the currently authorized or filtered view. It is advisory rather than a global project-completeness proof.
- The old full Native Python release gate has previously reported 30 failed modules out of 204; its new status was not re-audited in this sprint. The narrow 65-test gate does not replace it.
- No packaged WebView2 EXE, signed installer, Windows real-profile upgrade, physical two-PC LAN, production TLS host, real phone or full accessibility manual QA was executed in this sprint.
- No push, deployment, installation or release performed.
