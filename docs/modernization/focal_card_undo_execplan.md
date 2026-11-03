# Scoped card Undo/Redo pilot (2026-11-03)

## Purpose / owner decision / exclusions

The owner requested independently implemented Focalboard-inspired reversible card actions, without copying AGPL code. Source baseline: private LocalForge `main` at `45f3a596abe1496147a0e2b2e453b8a93de80624`; implementation branch and isolated worktree `feat/focal-undo-20261103` / `D:\CoS-Test\madar-focal-undo-20261103`.

The feature never replays invoice/accounting commands, monetary values, checklist payment state, archive, trash, ordering, attachment operations or workspace/board administrative changes. No installed binary or real profile is changed.

## Existing behavior / entry points

`src/App.jsx` stores full task-manager state via `change()` and debounced `api.saveState`. LAN saves carry remote revisions and may be rejected after concurrent edits. `taskUpdate` handles card editing and `toggleCardComplete` delegates to it. Existing financial fields are embedded in task objects, so full-card replay would be unsafe. The frontend originally had no general-purpose card undo stack.

## Design / parity specification

`src/card_undo.js` records up to 40 in-memory actions consisting of card identity, original complete card state for guards, allowed changed keys and new values. Only title, description, priority, due date, completion flag, text direction, labels, label colors and color cover are allowed. A reversal restores exclusively those allowed keys and assigns a new update timestamp, retaining monetary fields and accounting references byte-equivalent. Before recording, it confirms the update changed only the targeted card and fields. Before applying, it confirms the current card matches the anticipated snapshot, apart from update timestamp, and that the card is in an active board/list.

The history belongs to the current personal user/workspace/board view, resets when scope changes or unsupported mutations or fresh external snapshots arrive, and is never persisted. It is disabled for LAN client/server modes and viewers: the existing host does not expose atomic per-card conditional reversal against another collaborator's revision. The UI exposes buttons and Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z outside editable input elements. New edits after Undo clear the redo branch.

## Implementation progress and validation

- `VERIFIED` synthetic pure-state card history unit checks for ordering, identity, concurrent mutation refusal, archived/deleted refusal, preservation of issued invoice reference and other financial fields, bounded history and duplicate callback safety.
- `VERIFIED` 45 tests passed, 0 failed across card history, card context, editor, checklist and ordering suites.
- `VERIFIED` a separate headless Chromium full-App synthetic UI test passed: drawer Undo/Redo, board keyboard Undo/Redo and preservation of existing invoice, cost and paid checklist fields. During the isolated Vite test, font requests from the dependency junction were outside the dev server allow list; the test did not visually assert font rendering.
- `VERIFIED` `npm run build` (Vite production bundle). Vite reports a non-blocking chunk-size warning.
- Real user-profile acceptance, two-system LAN acceptance and installed EXE verification are **not run** in this isolated source pilot.

## Surprises / decision log

Baseline tests initially could not load `esbuild` because a new Git worktree had no `node_modules`. A local test-only Windows junction to the existing checkout's dependencies allowed the synthetic tests and build; it is ignored by Git and not part of the change. Whole-state LAN concurrency was the reason for deliberately refusing network Undo/Redo.

## Acceptance / rollback

Validate with `node --test tests/card_undo.test.cjs tests/card_undo_ui.test.cjs tests/card_editor_next.test.cjs tests/card_editor_interactions.test.cjs tests/card_context_next.test.cjs tests/cardextras.test.cjs tests/cardorder.test.cjs`, then `npm run build` and `git diff --check`. Roll back by reverting only this branch's commit; the history has no stored migration or user data footprint. The prime agent must integrate and verify any later changes to `App.jsx` against concurrent feature branches before a release.
