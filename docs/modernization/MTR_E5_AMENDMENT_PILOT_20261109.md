# E5 amendment-review preview | isolated synthetic pilot | 2026-11-09

**Status:** Implemented and verified at the stated synthetic-test scope. Baseline HEAD: 32bd8ff. The source of truth is still private LocalForge main.

## Scope

Refine 6.17–6.25 and 6.27, acceptance cases AC-20–28 and AC-30: independent amendment IDs with original and rejected amendment links; separate acknowledgment of open vs possibly duplicate amendments; field-by-field conflicting proposals and explicit human choices; targeted stale-baseline re-review; and reason-backed rejected-field suggestions without guessing ambiguous causes.

New module: mtr_amendment_review_preview.py. New tests: tests/test_mtr_amendment_review_preview.py. The existing mtr_finance_workflow_contract.py public API is reused without modification.

## Pure interface

- preview_create_amendment: Creates a candidate only after two distinct warning acknowledgments when both warnings apply; separately records actor, time and referenced amendment IDs in in-memory review events.
- review_field_choices: Only an authorized reviewer can choose a value for an actually conflicting field. Returns a new draft and an audit-intent event.
- preview_manual_submission: Requires an explicit manual-send action; blocks unresolved conflicts, original version mismatch, changed related proposals and affected baseline values. Returns only a preview decision, never a send.
- review_changed_baseline: Requires explicit chosen values for changed proposal fields, acknowledgment for changed dependencies and acknowledgment of a changed revision. Unaffected values are preserved.
- preview_rejection_guidance: Accepts only a host-verified Taraz rejection. Structured, explicitly identified affected fields produce a before/proposed comparison with no invented correction; empty, ambiguous or unstructured reasons produce manual-completion and financial-clarification actions.

No financial ledger, network, clock, database or original document is mutated. Cross-organization and other-project records are filtered from related previews, and out-of-scope source/receipt requests fail with identifier-free errors.

## Dependencies and limits

These are pure source contracts. Host identity, organization/project grants, verified Taraz origin, and timestamps are caller assertions and must be server-validated before real use. Production dispatch needs atomic version compare-and-send, audit persistence, replay defense and an independently authorized manual action. The pilot does not implement any such dispatch.

Potential duplicates are flagged only for identical field/value sets. Fuzzy thresholds have not been approved or measured. Values are bounded immutable scalars. The standalone Refine 6.24 document appeared garbled in text output; the integrated AC-27/AC-28 criteria and the unambiguous selection record informed rejection guidance.

## Observed validation

Command: py -3.12 -B -m unittest -q tests.test_mtr_amendment_review_preview tests.test_mtr_finance_workflow_contract

Result: **Ran 56 tests in 0.012s; OK, exit 0**. That is 29 new E5 tests and 27 adjacent workflow-contract tests. Python compilation of both new files passed. git diff --check exited 0, but does not inspect new untracked files. No runtime wiring, real Taraz request, real account, browser, cross-device, installer or production tests took place.

**Gate:** No commit, push, deployment, financial posting or production use.
