# Change Boundaries and Multi-Agent Coordination

## Before modifying anything

1. Inspect `git status`, branch, `HEAD`, origin and upstream; read current project instructions and active handoff.
2. Identify source-of-truth files and directories, data stores, live deployments and protected snapshots.
3. Name the specific owner and file scope for concurrent workers. If ownership overlaps, coordinate before editing.
4. Use an isolated clone or worktree when a task could collide with ongoing edits.
5. Respect existing Git history: never reset, clean, stash, force-push, rewrite a shared commit or delete another agent's artifacts without explicit owner authorization.

## Safe progress without repeated interruptions

**Proceed** on scoped read-only inspection, reversible local edits, focused tests, and evidence gathering under the user's existing authorization. Document ordinary assumptions briefly rather than requesting unnecessary confirmation.

**Stop the risky part, not all useful work**, on ambiguity involving live financial/customer data, credentials, network exposure, destructive cleanup, production publishing, privilege escalation, model spending, license incorporation, or an unresolved security gate. Prepare a safe draft or dry run and report the precise approval or missing fact.

Authorization to add a coding standard is not authorization to deploy unrelated products, change accounting records, or publish a different repository.

## Multiple agent rules

- Give each worker an isolated path or explicit non-overlapping owned files.
- Treat completed tests, commits and review reports as *claims to verify* before merging.
- Integrate by explicit commit SHA and inspect diffs, conflicts, tests and parent lineage.
- Never overwrite a worker's dirty tree or use `git checkout --` to resolve an ownership conflict.
- The integration owner validates combined behavior after merges; individual green test results cannot prove the combined state.
- If simultaneous workers modify the same boundary, stop mutation of that boundary, reconcile evidence and ownership, and then proceed.

## Git and deployment are separate gates

Local edit → focused verification → review/diff → commit → authorized push → remote SHA verification → separately authorized release/deployment → live verification.

Report the highest **actually verified** gate. A pushed commit is not a deployed version; a clean tree is not a validated release.
