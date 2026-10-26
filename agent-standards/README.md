# Shared Agent Engineering Policy: Madar Desk

**Status:** Activated for Codex, Claude Code and Cursor through root instruction entry points. This is a documentation-only change, not a new accounting runtime, database migration or application release.

## Read and apply
Start with [coding principles](core/coding-principles.md), [change scope](core/change-scope.md), [verification rules](core/verification-rules.md) and the [Madar profile](projects/madar-desk.md). Root [AGENTS.md](../AGENTS.md) and the owner's task and project decisions have priority over generic conventions.

The common workflow is: investigate assumptions, prefer the smallest acceptable solution, limit edits to the authorized scope, and test concrete acceptance checks. Ordinary reversible ambiguity should not become a repeated approval request; security, data-loss, financial and production actions retain their exact approval gates.

## Canonical source and provenance
The core rules and Madar profile are **verbatim copies** of the standards in private LocalForge forgeos.git at commit 783e9e6c07ca6f3d14d7e95ac245fc22af27d8ae. Updates are reconciled through reviewed per-repo commits. There is no live cross-repo sync or ForgeOS runtime dependency.

The ideas are independently written adaptations inspired by [multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills), under REFERENCE_ONLY; this is not an official Andrej Karpathy project. No upstream plugin or code is installed.
