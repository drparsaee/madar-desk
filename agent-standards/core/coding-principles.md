# Four Practical Coding Principles

## 1. Establish the actual problem

- Inspect the existing implementation and tests before proposing replacement code.
- Distinguish facts from assumptions and record uncertainty that materially affects correctness.
- Where requirements have multiple reasonable meanings, first look for an existing project decision, schema, test or user instruction.
- Continue with a reversible, low-risk interpretation when the ambiguity does not prevent success. Ask only when a missing decision can cause serious loss, unsafe access, an irreversible change or materially wrong delivery.
- Explain a simpler or safer solution when it better meets the stated goal. Never turn an optional improvement into a blocking debate.

## 2. Choose the smallest adequate solution

- Prefer reusing functioning project primitives over introducing competing state stores, frameworks or generic abstractions.
- Build the functionality currently requested. Avoid speculative configuration, premature optimization and unused extension points.
- Keep necessary validation, security boundaries, audit and failure handling; simplicity does **not** permit skipping required safeguards.
- Treat the existing project architecture, interfaces and naming conventions as constraints unless the owner explicitly changes them.

## 3. Make scoped, reviewable changes

- Map each edited line to the task or a required fix caused by that task.
- Do not reformat adjacent files, refactor unrelated code or delete old files simply because they appear obsolete.
- Preserve pre-existing uncommitted work, another agent's files, historical evidence and user data.
- Remove dead imports or resources only when **your own change** created them, after checking references.
- Keep commits focused; stage explicit paths, never blindly stage everything in a shared worktree.

## 4. Prove the outcome

- Translate the requested outcome into acceptance checks before implementation.
- For a bug, reproduce it or explain why reproduction is impossible, then run a targeted regression.
- For new behavior, cover meaningful success, failure and authorization cases.
- Run relevant existing tests and checks after editing. Tests are evidence, not a substitute for real runtime or deployment validation.
- Report exact observed results. Do not claim completion, production readiness or synchronization based on assumptions.

The goal is dependable progress with minimal churn, not more ceremony per trivial change.
