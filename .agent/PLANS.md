# Codex ExecPlan standard for Madar Desk

Adapted from [OpenAI Cookbook: Modernizing your Codebase with Codex](https://developers.openai.com/cookbook/examples/codex/code_modernization) (2025-11-19). This is a project workflow, **not** a separately installed Codex plugin.

## When to use

For changes affecting financial truth, storage, backup/restore, authentication, LAN, build/install, or shared architecture, write a self-contained ExecPlan under `docs/modernization/` **before** changing behavior. A small warning fix with a targeted test may not need one.

## Required ExecPlan sections

1. **Purpose / user decision / exclusions:** name the owner requirement and out-of-scope areas, identify the owning worktree and Git starting SHA.
2. **Existing behavior:** exact file/function references, entry points, persistent state, and business rules; distinguish runtime facts from previous reports.
3. **Plan of work:** ordered, independently reviewable steps with precise file paths.
4. **Parity specification:** expected output and side effects for normal, edge, error and repeated-run cases, including exact schema/currency/permission invariants.
5. **Progress:** `TODO`, `IN PROGRESS`, `VERIFIED`, or `BLOCKED` with real evidence (command and test result). Never mark skipped checks as passed.
6. **Surprises / decision log:** dated facts, hypotheses explicitly labelled as such, alternatives considered and reasons for any deliberate behavioral difference.
7. **Validation and acceptance:** automatic tests, original-versus-modernized comparison, rollback, installation boundary, negative checks, data protection, and remaining manual acceptance.

## Madar-specific release gates

- Never run preflight/installer/restore against a real Madar or Parsian profile during modernization. Isolate **all** `APPDATA`, `LOCALAPPDATA`, database and binary fixtures.
- Source must remain in private LocalForge Git. A worktree branch and a local commit are **not** a remote push or deployed release.
- The canonical accounting unit is **rial**; historical toman cannot be silently converted. Preserve identifiers, ledger balance, idempotency, ACL and rollback.
- For installers: no overwrite of old versioned binaries, no mutation of user profile by the package, and no activation on backup/hash failure.
- Run targeted tests, adjacent tests, relevant regression suites, and `git diff --check`. Record failed and unrun checks. If full suite is red, release status remains `BLOCKED`.
- Before major edits, update `overview`, `design`, and `validation` docs, and prefer a small measured pilot over mass rewrites.

## Minimal reusable template

Copy the headings above into `docs/modernization/<pilot>_execplan.md`, link sibling `_overview.md`, `_design.md`, and `_validation.md`. Specify a stable baseline commit for side-by-side testing. Do not equate the planned tests with tests actually executed.
