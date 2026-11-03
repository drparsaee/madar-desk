# Focalboard-inspired Madar enhancements: provenance and boundaries

Reference reviewed: [mattermost-community/focalboard](https://github.com/mattermost-community/focalboard), default branch `main`, 2026-11-03.
This is a design reference, **not** a vendored source dependency.

## License boundary

Focalboard's `LICENSE.txt` states the principal source is AGPL-3.0 with
additional terms or commercial licensing. A subset of administrative tools
and configuration files is Apache-2.0; compiled Mattermost binaries have a
separate MIT grant. These grants must **not** be treated as an MIT license for
all source files. None of the original Focalboard implementation is copied
into this change. Features below are independently authored for Madar's
existing React, SQLite and LAN contracts. Review license obligations before
any future direct reuse.

## Relevant ideas and Madar adaptation contract

| Focalboard source/reference | Useful idea | Madar-specific constraint |
| --- | --- | --- |
| `webapp/src/blocks/boardView.ts` | Per-board presentation state: view, sort, hidden columns, grouping | Persist by board/user, no change to canonical task records |
| `webapp/src/blocks/filterGroup.ts`, `webapp/src/cardFilter.ts` | Nested AND/OR conditions | Bounded recursive validation, reject malformed state, respect user visibility |
| `webapp/src/undomanager.ts` | Grouped reversible commands | Only safe local task actions, never finance issuance or cross-LAN stale writes |
| `webapp/src/components/table/tableColumnResizeContext.tsx` | Resizable table columns | Bound widths and prevent overflow; accessibility and RTL |
| `webapp/src/components/kanban/calculation/calculation.tsx` | Column summary values | Count only eligible visible tasks; never report drafts as revenue |
| `import/notion/README.md` | Import a Notion table export as a fresh board | Local CSV only; bounded, previewed, additive, no automatic finance data |

## Importer safety checks

The independent Notion CSV module accepts a single table with a Name/Title
column. It has a 3 MiB input limit, 2,000-row limit, 50-column limit,
40-stage limit and bounded text fields. It rejects malformed quotes and row
width mismatches. Only a new project/board and new tasks are added; existing
records are preserved. The importer never executes formulas, imports financial
records or binds users/ACLs from untrusted export data.

The importer is intentionally a subset of a full Notion export: images,
attachments, comments, rich-page trees and multi-table relationships are not
imported. Separate acceptance is needed for real-world Notion exports.

## Integration and verification

- All functional code must use isolated worktrees and synthetic test profiles.
- Merge into LocalForge `main` only after deterministic targeted and final
  source QA pass; do not force-push or overwrite live user data.
- An installed EXE and public updater release are separate release gates.
- Preserve existing Trello JSON import and its contract tests.
