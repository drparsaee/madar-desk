# Trello board design reference for Madar Desk

Capture date: **2026-10-27**. Purpose: a **reference for the Kanban/Task Manager UI** only. This folder does not modify the running application.

## Evidence and confidence

| Evidence | Source | Status |
| --- | --- | --- |
| Live public board and screenshot | [Trello Development Roadmap](https://trello.com/b/nC8QJJoZ/trello-development-roadmap), Chromium via `playwright-cli` | **Observed** in an anonymous browser, with the welcome dialog dismissed and only necessary cookies selected |
| Computed styles / bounding rectangles | `board-runtime-observed.json` from the same page | **Measured** on a 1280 × 720 desktop viewport |
| Static color/font/animation scrape | SkillUI v1.3.4, `trello-public-board-design/` | **Raw automated output**, not a verified specification; a number of semantic guesses are wrong |
| Public marketing site scrape | SkillUI v1.3.4, `trello-public-web-design/` | **Insufficient**: no colors/components were found |
| Behaviors, actions and themes | Atlassian's [Trello guide](https://trello.com/guide/create-project), [list color documentation](https://support.atlassian.com/trello/docs/change-the-color-of-a-list/), and [design tokens](https://atlassian.design/foundations/design-tokens) | **Documented** by the vendor, not measured in this read-only session |

The reference screenshot is `verified-board-clean.png`. It shows the **actual public board** rather than the Trello marketing landing page. Do not use `trello-public-board-design/screenshots/homepage.png` as evidence of board UI: the generated screenshot displays an incomplete marketing page.

## Measurements from the live board

All values are **observations for this one board, viewport and session**, not contractual constants of all Trello versions. Values are rounded to whole CSS pixels.

| Element | Measured value | Evidence |
| --- | --- | --- |
| Outer column wrapper | **284px** width, horizontal padding **6px** on each side | `list-wrapper` |
| Column/list surface | **272px** width, **12px** corner radius | `list` |
| Column surface background | **#F1F2F4** | `list` computed background |
| List header | **40px** tall; top/side padding `8px 8px 0px` | `list-header` |
| Card surface | **256px** wide, **8px** radius | `trello-card` |
| Card background | **#FFFFFF** | `trello-card` |
| Card gap | **8px** example spacer | `list-card-gap` |
| Primary card text | **#292A2E** | `trello-card` computed color |
| Secondary/list text | **#505258** | `list` computed color |
| Font family in board UI | `"Atlassian Sans", ui-sans-serif, ...` | computed styles of `board-view`, `list` and `trello-card` |
| Header over board | **56px** high in observed DOM | `board-header`; note more than one matching node was present |
| Card shadow example | `0 1px 1px rgba(30,31,33,.25), 0 0 1px rgba(30,31,33,.31)` | `trello-card` |

**Not measured:** a fixed list height, the authenticated add-list menu, editing a list title, drag/drop animation timing, dark theme appearance or mobile-specific layouts. The read-only public board exposes no authoring controls. Component heights vary with content and available viewport space.

## Design rules suitable for Madar

1. Use content-sized, **fixed-width Kanban columns** with horizontal scrolling rather than distributing them to fill the whole board.
2. Keep the **list header and its actions inside the list surface**. The actions button belongs alongside its own list name.
3. Use a visually separate, narrow **Add another list** entry at the end of the horizontal list row, rather than stretching all columns.
4. Put cards inside their list with short vertical gaps and clearly separated raised surfaces.
5. Keep actions attached to their owning list/card. For Madar's RTL UI, mirror **placement and focus order**, not labels or icon semantics blindly.
6. Preserve independent list/card scrolling, responsive viewport clipping, keyboard focus, menu accessibility, and light/dark theme contrast.

Rules 1–4 are **adaptation guidance**, using measured layout plus Trello's [documented list/card workflow](https://trello.com/guide/create-project). They are not evidence that we exercised all editing actions.

## Tokens and reuse

- `trello-board-reference.css` contains deliberately namespaced, **observed-only** design constants; it is **not imported into Madar**.
- `SKILL.md` tells a coding agent how to reuse this reference with correct evidence boundaries.
- Source-of-truth vendor tokens should follow semantic names such as `color.text`, `color.background.*` and `elevation.surface.raised` rather than mapping every page color directly into Madar. See [Atlassian design tokens](https://atlassian.design/foundations/design-tokens) and [elevation](https://atlassian.design/foundations/elevation).

## Reproduce

```powershell
skillui --url https://trello.com/b/nC8QJJoZ/trello-development-roadmap --name Trello-Public-Board --out . --format both
```

SkillUI's static scrape generated raw markdown, a SKILL and packaged assets, but its own screenshot did **not** faithfully capture the board. A browser measurement was therefore added. The generated raw folders and downloaded font binaries remain local and untracked, to avoid mistaking automated guesses for verified design decisions or redistributing bundled fonts.

**Limitations:** This is a public, anonymous browser view of a sample board. It is neither Trello's source code nor a complete reverse engineering of authenticated Trello. Some observed console errors did not prevent the board from rendering; functional interaction coverage is not established.
