# Next version | Card editor, global search, provider-neutral accounting

## Scope and source

- Initial baseline: private LocalForge origin/main a6714ec.
- Separate throwaway worktree for development. No user AppData, company ledger, Parsian backup, LAN service or installed EXE is an input.
- Search module was independently developed and cherry-picked from worker commit 7510771. Provider-neutral CSV preflight is a separate isolated project and must be integrated only after review.

## User requirements implemented in the source

1. Toolbar order follows the matching card content order. Metadata fields are compact. Due-date click opens a small Persian/Gregorian month picker and emits canonical ISO date.
2. Assignees, time management, dependencies/blockers and reports are controlled disclosures. State is saved in a local per-username preference, not on the card. A second card reuses the choices. Different users have independent choices.
3. Old tall color covers are preserved in data but displayed as a small horizontal strip **after** the task title. New cover edits always generate strip type.
4. Native color inputs retain free selection; common named swatches are added for priority, labels (including new), avatar, list and invoice template colors.
5. The card drawer has a reversible archive action in addition to trash. Exact IDs, monetary fields and attachments are not deleted.
6. The historical Toman-to-Rial card action is removed. Nonzero old Toman price remains read-only and is not automatically interpreted as Rial. Newly entered sales amounts are explicitly Rial.
7. Global search shows active, archived and trash tasks with the exact visible list/project/board and scoped grants. User can sort by last change or list/card order. Source data and finance objects are not rewritten.

## QA evidence and exclusions

- Targeted new JSX/source/Playwright tests for multi-card shared preferences, popup ISO selection, cover placement, archival and archive search passed.
- Targeted 36 Node tests across new card search + editor functionality passed after integration. Vite build passed.
- Initial full safe npm test had one Python module error. The separate repeatable synthetic Python suite was rerun with a retained JSON diagnostic report and passed 180/180 modules, 1667 tests reported, with two skipped and two expected failures. Full post-merge release QA remains mandatory.
- All Python tests use isolated disposable APPDATA and USERPROFILE. No packaged EXE launch, real-host recoverability, physical two-machine acceptance, proprietary accounting binary import or GitHub publication is claimed.
