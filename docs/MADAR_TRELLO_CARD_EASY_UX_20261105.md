# Madar Desk: Trello-like card simplicity pass

Date: 2026-11-05. Source branch: `feat/madar-ux-execution-20261104`, starting from `8f8321dd`.

## Goal and preservation contract

Make ordinary cards easier without removing their established features or changing task data schema, accounting bridges, issue/posting behavior, host ACL/CAS, backup semantics, or the user's Vitrea/Estedad RTL design language. This is an incremental card-detail UX pass, **not** proof of full Trello parity or production readiness.

## Implemented

- On desktop, task details use a centered, rounded dialog. On narrow screens, the same details occupy the viewport.
- The title is followed by a project/list breadcrumb and concise contextual chips for priority and populated due date, assignees, and labels.
- Five high-frequency navigation actions appear first; attachments, cover, time, dependencies, and reports remain reachable via **More**. All original disclosure sections and per-user preferences remain intact.
- A new user's checklist starts expanded. Clicking checklist or description navigation focuses the input so a single action reaches typing. Previously saved disclosure preferences are honored.
- Title input is capped at 300 characters to avoid the native host's stricter save rejection.
- Context-menu archive/delete now require separate confirmation and support cancellation, matching safety already present in the detail drawer.

## Independent review / REA evidence

- An ECC-style independent, read-only reviewer checked persistence, role/CAS, title validation, undo, and context actions. This is **not** a claim that the entire ECC harness or an autonomous multi-model council ran. Reviewer identified the missing title cap and destructive one-click context actions; both were corrected in this pass.
- Existing REA 6.7.0 was run locally against **five copies of our own unminified source files** (`App.jsx`, `boardplus.jsx`, `card_context_menu.jsx`, `card_section_preferences.js`, `card_undo.js`) without launching or inspecting Trello. Exit 0, five files parsed, zero parse failures, 37,094 AST nodes; 343 syntactic findings are observations, **not** 343 confirmed bugs.
- Evidence ID: `ev_92fd9cc724e4ca74cd8ccd5e7d45e22e20ffa026af6ce55bd06ab1e7b5f9df23`.
- Local QA artifacts (not version-controlled): `D:\CoS-Test\madar-ux-evidence-20261105\rea-card-static.json`, `rea-card-static-progress.log` and `trello-card-full-node-final.log`.
- REA's inert static parse does **not** prove browser execution, visual correctness, or Trello parity; real-browser tests cover bounded interactions separately. No authenticated Trello data/bundles were inspected.

## Verification and scope

- `npm run build`: PASS; JS chunk >500 KB warning remains nonfatal.
- Targeted card/browser tests: 16/16 PASS, covering modal centering, native keyboard/focus, More disclosure, checklist creation, description edit, date/calendar, archiving, and confirmation cancel/commit.
- Additional targeted full-App browser geometry tests for calendar and card density at 1440/480 px passed.
- Full JavaScript regression and accessibility suite: **692/692 PASS, 0 FAIL, 0 SKIP, exit 0** with concurrency 2 (verified from the completed process and `trello-card-full-node-final.log`). Exact `axe-core 4.14.0` was installed only into an isolated QA dependency directory, not shared app dependencies. Its existing accounting acceptance test reports **48 scans** across four widths, two themes, and six page/wizard states without serious/critical findings.
- The earlier first full-suite pass was **689/692**: one test assumed checklist was closed, one theme test timed out under higher concurrency, and one accessibility test lacked the exact local dependency. The checklist test now observes the disclosure state, theme/header tests passed independently, and the isolated dependency plus full lower-concurrency rerun resolved all three. The recorded evidence is for synthetic test fixtures, not live customer data.
- Production installation, manual UX acceptance, real two-PC LAN and complete Trello parity were **not** performed by this pass.

## Explicit follow-up risks, not claimed solved

- Existing-card editor still auto-saves with a delay, without a drawer-local acknowledged-save indicator. Errors and CAS recovery must never appear as successful saves.
- Keystroke-level card Undo grouping is not yet one meaningful edit per Undo action.
- Context-menu Move opens metadata rather than focusing the list/board destination.
- User preference for older saved disclosure layouts remains authoritative; these users may still have checklist initially collapsed. This is intentional non-destructive preference preservation.
