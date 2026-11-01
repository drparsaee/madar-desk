# Trello design-system extraction status

Date: 2026-10-27
Tool: skillui 1.3.4
Target: https://trello.com

## Completed
- Public marketing website static extraction completed with exit code 0.
- Output: static/trello-public-design/DESIGN.md, SKILL.md, CLAUDE.md, .skill package, screenshots/homepage.png and downloaded fonts.
- SkillUI reported 199 CSS colors, 0 computed colors and 672 font declarations during fetch; final DESIGN.md reports a filtered palette of 20 colors, 3 font families, and 7 component categories/patterns. These are tool counts, not independent verification of Trello's internal design system.
- Extracted examples include CSS tokens, Charlie Text/Charlie Display references, 4px spacing grid, layouts, shadows, component snippets and responsiveness sections.

## Incomplete
- Ultra visual extraction failed before screenshot/interaction journey. Playwright reported missing chromium_headless_shell-1248 executable. Browser download was attempted but did not complete and was canceled.
- Internal authenticated Trello board, list, card, dialogs, drag-and-drop and settings interface were not inspected.
- No claim of pixel-perfect fidelity or reusable internal Trello component specifications can be made.
- Generated semantic token roles and typography section may be approximate or mislabeled. Do not reuse as canonical without manually inspecting runtime CSS/DOM.
- Static output does not include separate JSON token files.
- This is reference material, not an implementation change. No git commit was created.

## Follow-up
- Supply an authorized browser session containing a non-sensitive example Trello board, or use public board pages; run browser visual inspection to document list widths, gutters, cards, menu placement, board overflow, modal and RTL differences.
