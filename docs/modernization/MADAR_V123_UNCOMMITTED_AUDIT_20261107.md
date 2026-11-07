# Madar 1.0.23 uncommitted-work reconciliation, 2026-11-07

## Boundaries

The immutable release base is `22dbf1e`, package `1.0.23`.
The native continuation is `feat/madar-v123-gantt-chat-20261107`; the independent web
continuation is `feat/madar-v123-web-integration-20261107`.
No installed software, personal task profile, Parsian data, or Taraz data was
changed by this audit.

## Audited inputs

1. Legacy desktop `madar-desk` on `main` / `1.0.13`: **10 modified tracked
   files, 52 untracked files**, including 46 static Trello design-research
   files. The six non-research untracked files were present in the native
   continuation. Modified collaboration, migration/export and test changes
   were included. The remaining `App.jsx` differences are changes to layout
   and task-only behavior in 1.0.23, not a reason to overwrite the newer UI.
   A LAN project deletion and cross-project task transfer are already
   blocked by the baseline's project-integrity checks.
2. Legacy web `madar-web-pwa-20261106` / `1.0.22`: **12 modified tracked
   files and 45 untracked source, test and deployment files**. All 45
   untracked files were present in the web continuation. Normalized source
   comparisons found no extra unmatched untracked files. Differences in the
   App/settings integration are intentional: web sync and card/project
   conversations are kept, while accounting screens and finance posting
   are not copied back into the 1.0.23 task manager.
3. Old PWA cache references to 1.0.22 were superseded by the 1.0.23 cache,
   and its install test was updated to discover the actual cache name.
   `package.json` on both continuation branches remains `1.0.23`.

The original dirty worktrees were **not reset or cleaned**. Trello research
assets remain available in the old worktree, but were not imported into the
executable without a demonstrated application requirement.

## Next development fix

Both native and web had an observable Gantt preference bug: the per-board
view-preference normalizer only accepted `board`, `list`, and `table`,
so selecting `gantt` could not survive reloading. The continuation changes:

- Explicitly accepts `gantt` in the existing per-user/per-board preference
  allowlist; preserves table configuration and rejects unknown modes.
- Uses the saved view of the newly selected board, not the previous board's
  Gantt selection. The global time dashboard stays separate.
- Falls back to board view if the current managed role hides Gantt.
- Uses board-scope React keys to reinitialize the Gantt axis for a new board.
- Persists web's Gantt click through the same preference API as native.

Test results and commit IDs must be reported only after they actually run.
The web release is not deployed, and the native EXE is not rebuilt or installed
by these source-only changes.
