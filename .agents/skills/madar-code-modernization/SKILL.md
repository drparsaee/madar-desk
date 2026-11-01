---
name: madar-code-modernization
description: Use for modernizing, refactoring, securing, upgrading, or migrating Madar Desk source while preserving Windows installation compatibility, user data, rial accounting invariants, and verified old-versus-new behavior.
---

# Madar Code Modernization

Use the [OpenAI Codex Code Modernization Cookbook](https://developers.openai.com/cookbook/examples/codex/code_modernization) as an engineering **workflow**, not as an automatically run migration tool.

1. Read repository `AGENTS.md`, `.agent/PLANS.md`, and relevant project decisions. Inspect branch, HEAD, dirty state, and the owning worktree before any code change.
2. Select **one bounded pilot** and write or update `docs/modernization/<pilot>_execplan.md`. Record the baseline commit, the exact modules and owner-required invariants.
3. Inventory actual entry points, files, storage, side effects, contracts, business rules, and callers in `<pilot>_overview.md`, with code-relative references.
4. Write `<pilot>_design.md` and `<pilot>_validation.md`: intended behavior, explicit differences, normal/error/boundary/idempotency scenarios, and old-versus-new tests. Use OpenAPI **only** when the boundary actually exposes HTTP; otherwise document the real CLI/event/file interface.
5. For source changes, run baseline characterization tests **before** editing. Apply the smallest compatible change in an isolated worktree. Compare outputs on synthetic identical inputs before/after. Keep all financial migration trials and customer data outside Git and outside test targets.
6. Use disposable `APPDATA`/`LOCALAPPDATA`, databases, and binaries for every QA run. Never launch an installer, restore Parsian, alter a live app, close a user's session, or make security-sensitive production changes without their separate acceptance gates.
7. Record exact commands, observed test totals, skips/failures, `git diff --check`, a second review when actually completed, local commit, remote SHA, and deployment as **separate** statuses. Do not call partial tests "full regression", or committed code "released".

Initial worked pilot: `docs/modernization/pilot_upgrade_execplan.md` and `tests/test_codex_upgrade_parity.py`.
