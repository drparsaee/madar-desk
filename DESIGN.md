# Madar Desk visual direction

Based on the craft and accessibility principles of juliobsz/skills (awwwards), adapted to a desktop utility.

## Brief
Personal, local-first Windows board for tasks, checklists, progress and manual agent updates. Persian RTL; no backend, account or ForgeOS requirement. Cloud transfer is an explicit Drive backup/restore action.

## Concept exploration
1. **Desk surface**: a tidy workbench with cards that settle into slots. Fit 5 / feasibility 5 / originality 3 / portability 3.
2. **Flight control**: task lanes as orbital trajectories. Fit 3 / feasibility 3 / originality 4 / portability 4.
3. **Personal notebook**: notes and tickets in a bound planner. Fit 4 / feasibility 4 / originality 3 / portability 4.

Chosen: **Desk surface**. One decisive gesture: drag a task into another stage and the destination quietly receives it. Function first, no loader or WebGL.

## System
- Surface #f7f8fa, white #fff, ink #1d2838, muted #778295, fine border #e8ecf0.
- Accent #3966d0; action accent #294fbd. Secondary washed blue, mint, amber, and lilac only for meaningful stage signals.
- Font: native Persian Segoe UI/Tahoma fallback; system UI for English numerals. No distributed font files.
- Grid: 248px sidebar, 100% board with five flex lanes, card gap 12px.
- Radius: 14px cards, 12px controls, pill badges.
- Interaction verb: **settle**. Quick translate + shadow on hover/drag; reduced motion honored.
- Background intentionally still, because prolonged movement interferes with daily work.
- Keyboard: visible focus, Escape closes dialogs, Enter submits. All principal actions have labels.
- Demo items explicitly flagged and removable. Empty state kept useful.

## Status of verification
Visual QA and executable verification must be recorded separately from the design intent.
