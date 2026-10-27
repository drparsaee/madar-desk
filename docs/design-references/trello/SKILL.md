---
name: trello-board-reference
description: Apply the inspected Trello board design reference to Madar Desk Kanban without importing Trello assets or inventing unobserved behavior.
---

# Using the Trello reference in Madar

Read `README.md`, `board-runtime-observed.json`, `trello-board-reference.css` and `verified-board-clean.png` in this directory before making UI changes.

## Evidence rules

- `board-runtime-observed.json` is a single **live browser observation** at 1280x720. It does not guarantee cross-device sizes or dark-theme mappings.
- `trello-public-board-design` is a raw SkillUI scrape. Some automatically inferred typography/theme roles conflict with the DOM. Never treat its `DESIGN.md` as authoritative without comparing evidence.
- The anonymous Trello board does not expose list creation/editing behavior. For these behaviors, consult documented Trello guides and the current Madar product specification.
- Never reuse Trello logos, downloaded fonts, artwork, or screenshots as shipped Madar brand assets.

## Implementation suggestions

Keep columns non-stretching (observed 272px surface width; 284px wrapper including horizontal padding), each with a header/actions menu *inside* the column. Separate the add-list affordance at the end of the horizontal scroller. Card surfaces are light, raised, rounded 8px; columns are rounded 12px and visually distinct. Adapt placements for RTL, account for nested scroll containers, focus states, responsive and dark themes.

The numbers are design reference, not an instruction to replace Madar's existing component system wholesale. Update only the user-requested UI, and test DOM behavior with real scrolling.
