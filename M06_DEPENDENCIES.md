# M-06: Card dependency DAG

Opt-in module `src/card_dependencies.js`. A card's optional
`dependencies: string[]` contains IDs of predecessor cards in the **same
project**. Operations are immutable and require an explicit administrator or
project-editor grant; those options are UI defense in depth, not server authentication.
The entire graph is checked for self-dependencies, duplicates, cycles,
missing/deleted predecessors and size limits (20,000 cards, at most 128
predecessors/card, 200,000 total edges). Topological order and critical path
use each card's explicitly recorded `estimatedMinutes`; absent estimates
are zero and the result is **not** a deadline forecast.

Public APIs:
`dependencyGraph(tasks)`,
`addCardDependency(state,cardId,predecessorId,{canManage:true})`,
`removeCardDependency(...)`,
`cardBlockingStatus(tasks,cardId)`,
`criticalDependencyPath(tasks)`.

No original task, cost, ledger, invoice, attachment, due date or journal is
altered. No automatic rescheduling and no rule execution are provided.
## Source integration (2026-10-21)

- Trusted native/LAN persistence boundary: `card_dependency_validation.py` is
  invoked by `native_app.is_valid` and rejects cycles, duplicate/missing/self
  references, soft-deleted predecessors and cross-project predecessors using
  bounded nonrecursive traversal.
- React `src/card_dependency_panel.jsx` is mounted in TaskEditor in Operations
  and Finance mode. It shows incomplete blockers and offers constrained
  add/remove, writing via the existing task update and host CAS path.
- `criticalDependencyPath` now uses predecessor pointers instead of copying
  every predecessor prefix (avoids quadratic memory on deep chains).
- Focused Python host and Node pure tests pass. A fresh full QA/EXE GUI test
  is still needed for the integrated current source.

**Still partial:** Today/Waiting/calendar linking, due-date change warnings,
real GUI and two-computer LAN persistence acceptance remain open. A referenced
predecessor cannot be soft-deleted and committed until references are detached;
no silent graph loss is permitted.
