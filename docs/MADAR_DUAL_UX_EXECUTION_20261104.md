# Madar Desk 1.0.13 — Accounting + Task Manager UX execution

Date: 2026-11-04. Owner decision: make both accounting and task management genuinely usable, not merely restyle AI-generated interfaces. Scope includes navigation, real end-to-end flows, predictable states, keyboard accessibility, RTL/responsive display, data correctness, and regression safety.

## Authority and boundaries

- Canonical source: private LocalForge `localadmin/madar-desk`, `main` at baseline `c9aaf3e4a9cd7653a620d3671ffc58f546c3d17e`.
- Implementation worktree: `D:\CoS-Test\madar-ux-execution-20261104`, branch `feat/madar-ux-execution-20261104`.
- UX reference: the already chosen Vitrea design system, RTL and Estedad. No replacement theme, artificial placeholder finance data, or unrelated capability expansion.
- Protect real accounting journals, Parsian backups, current installation, credentials, actual customer/task data, and LAN access. Browser tests must use synthetic, isolated fixtures.
- An ECC-style review/rework/test loop is used; installing ECC alone does **not** prove an autonomous multi-agent team or UX acceptance.

## Execution phases and gates

| Phase | Accounting | Task manager | Exit evidence |
| --- | --- | --- | --- |
| 0. Baseline | Identify invoice, navigation and journal data boundaries | Identify boards, cards, list and identity boundaries | LocalForge SHA, clean isolated worktree, baseline targeted tests |
| 1. UX audit | Search, invoice workflow, corrections, parties and payment | Board navigation, list menu, card completion, saved filters | Screens and exact steps for each observed defect; source-only findings labelled |
| 2. Shared UX standard | Form validation, keyboard/focus, RTL, state copy | Consistent dialogs, focus, feedback, empty/error states | Reusable interaction rules plus browser tests |
| 3. Task manager pilot | Keep finance bridges and source IDs unchanged | Fix board menu, correct completion analytics, isolate saved filters | Chrome keyboard test + completed-task report test + multi-user/board persistence test |
| 4. Accounting pilot | Fix search keyboard selection and misleading issued-invoice correction CTA | No implicit financial posting on task completion | Chrome search test + invoice correctness tests |
| 5. Extended flow rebuild | Invoice, correction, receipts, purchases, bank and reports | Card create/edit/drag/duplicate/archive/restore/filters | End-to-end screenshots, accessibility checks, denial/rollback tests on synthetic data |
| 6. Integration/release | Host ACL, rial unit, GL/idempotency, installer and profile isolation | LAN, persistence, responsive/light-dark, recovery | Full safe-suite + independent installed EXE and user workflow acceptance |

### Immediate pilot findings, bounded to evidence

| ID | Evidence before patch | Pilot action | Gate |
| --- | --- | --- | --- |
| UX-A01 | `accounting_global_search.jsx` caught Enter bubbled from a focused Close/result button and could open the highlighted record instead | Handle Enter selection only when the search input owns focus | Synthetic Chrome with Close, second-result and input Enter |
| UX-A02 | Issued-invoice correction review button said `ذخیره پیش‌نویس`, but the handler emits `invoice.correct` that reverses an issued document | Clearly label reversal + replacement draft before submission | Source and adjacent regression; full correction E2E still open |
| UX-T01 | Portalled list menu did not move keyboard focus inside, and focus outside closed it | Focus first enabled control after opening; Escape returns to trigger | Synthetic Chrome |
| UX-T02 | `completed:true` without stage `done` stayed overdue and counted unfinished | Count explicit completion without moving status/listId, which could trigger finance operations | Pure-function and reporting tests |
| UX-T03 | Saved filters used a shared localStorage key across users/boards | Namespace by host-authenticated identity and board; do not import unattributed legacy key automatically | Synthetic Chrome identity/board switch |
| UX-T04 | The currently active filter survived user/board switches even when saved presets were separated | Scope controlled filter state before rendering by authenticated host identity + board | Browser identity/board switches and state-contract regression |
| UX-T05 | Nested overdue rules and a legacy `done` stage ignored the explicit completion toggle | Use the same tri-state completion predicate in reports, basic and advanced filters; explicit `false` overrides legacy stage | Targeted pure-function tests for completed true/false/absent |
| UX-A03 | Cancelling navigation away from an unsaved invoice closed Ctrl+K search and lost the query | Propagate navigation veto from `gotoTab` through record/section selection and keep search open; Ctrl+K focuses existing dialog | Integrated synthetic Chrome accounting workflow |

The legacy `madar-saved-filters-v1` key is **not removed** and is **not loaded automatically** because ownership of its contents cannot be determined safely. Explicit user-reviewed migration can be considered later; present changes do not delete it.

## Follow-up scenarios to capture and accept

1. Task manager: create and edit card without lost unsaved text; drag card with keyboard fallback and stable order; edit checklist and dates; archive and restore; board/list move with accurate focus/feedback.
2. Task manager: saved filters across two boards, two LAN users, and host changes; completed cards excluded from overdue counts; search results open precisely the selected card; dark/light 390/768/1440 RTL visual verification.
3. Accounting: create and save invoice draft; change customer and line quantities; review, confirm and issue with exact rial totals; cancelled unsaved navigation retains work.
4. Accounting: correction of issued invoice clearly identifies irreversible ledger impact and requires confirmation; wrong role cannot issue/correct; return, receipt and payment preserve idempotency and audit trail.
5. Integration: card-to-sales and checklist-to-purchase handoff preserves source ID and draft-only boundary; no silent posting from task status/UI events.
6. Release: native EXE real-window acceptance on a disposable profile, financial data safety and recovery, LAN two-PC acceptance.

## Progress and validation

- Baseline: targeted Chrome/Node tests passed before edits; two read-only workers supplied source-grounded UX candidates.
- Initial focused Node/Chrome subset after A01/T01/T02: 19/19 PASS, 0 skipped; saved-filter and neighboring browser subset: 11/11 PASS, 0 skipped.
- Extended scoped tests with tri-state completion, active scope and keyboard: 29/29 PASS, 0 skipped. Accounting integrated UXFocus/navigation tests: 12/12 PASS after correcting Ctrl+K focus while an existing dialog remains open.
- Vite production build succeeded once after most of these edits; a final build after integration fixes remains an explicit gate.
- Full Python safe suite has **not** passed: first isolated run executed 198 modules, 197 PASS, one error (module name missing after runner cleaned disposable report). Second persistent run executed 198 modules, 197 PASS, one TIMEOUT in `test_standalone_accounting_auto_backup.py` at per-module 120 seconds. Further isolated diagnosis is separate from marking the whole suite green.
- Full source-suite, native-EXE acceptance, live database/ledger, 2-PC LAN, full screenshot-based UX audit, integration into `main`, and publication remain independently open until supported by evidence.

## Safe rollback

Only the separate worktree changes source at this stage. Do not reset/clean `main`; do not delete pre-existing Trello research directories. If a pilot fails full regression, leave the canonical branch unchanged, fix or isolate the offending commit, and rerun adjacent tests. Actual installed app and databases are out of scope.
