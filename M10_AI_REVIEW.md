# M-10 | AI proposal, human review, provenance and undo plan

**Scope and evidence (2026-10-21).** Independent Python preflight in
`ai_change_review.py`, exercised by synthetic tests in
`tests/test_ai_change_review.py`. These files neither register an AI model nor
mount any API handler. They import only Python standard-library modules; no
APPDATA, database, filesystem, HTTP, OS commands, Git, live accounts, or model
provider are read or changed.

Current host observation (read-only): `mcp_stdio_v1.py` publishes three
**read-only** tools, `madar_list_projects`, `madar_list_cards`,
`madar_get_card`; it has no AI mutation operation. In
`integration_api_v1.py`, the existing card PATCH permits only
`title` + a 64-character hexadecimal state `revision` with a separate
idempotency key and normal LAN role/project checks. M-10 is **not wired to
either surface**. Its interfaces and security assumptions below are an
integration contract, not an end-to-end QA claim.

## Exact proposal shape

External model output should enter through
`decode_proposal_json(raw_json_bytes)`, which accepts only strict UTF-8 JSON
objects, rejects duplicate properties at every depth, NaN/Infinity, malformed
JSON and inputs above 16,384 bytes. Nested schema and field checks then occur
in `validate_proposal`, which also enforces the full key allowlist and
canonical serialized size at most 16,384 bytes:

```json
{
  "schemaVersion": 1,
  "proposalId": "proposal-001",
  "taskId": "task-123",
  "projectId": "project-1",
  "expectedRevision": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "changes": {"title": "بازبینی طرح", "priority": "high", "dueDate": "2026-10-25"},
  "provenance": {
    "source": "ai",
    "provider": "local-model",
    "model": "model-id-from-host",
    "inputSha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
    "evidenceIds": ["task-123", "report-123"],
    "generatedAt": "2026-10-21T12:00:00Z"
  },
  "usage": {"inputTokens": 200, "outputTokens": 100, "estimatedCredits": 75}
}
```

`inputSha256`, `provider`, `model`, `generatedAt`, `evidenceIds` are
**declared provenance**, not proof that those sources/models really generated
the text. The trusted host must construct/corroborate metadata from actual
model invocation and restrict evidence identifiers to material visible to the
requesting user. It must not pass task finance fields to the model.

Only **three scalar task fields** are editable: `title` (1–160 printable
characters), `priority` (one of the host-supplied values), `dueDate` (strict
ISO `YYYY-MM-DD` or empty). Every proposed field must actually change its
current value. No additions/deletions of tasks or mutations of nested objects.
Unknown fields, roles, permissions, finance/accounting/GL, project amounts,
card costs/checklist costs, files, code, scripts, tools, URLs, integrations,
and **status changes** fail closed. Status is intentionally excluded here:
completed-card transitions can induce invoice or automation side effects in the
existing host. Readable M-10 behavior must not accidentally activate them.

## Python API (pure)

```python
from ai_change_review import (
    decode_proposal_json, validate_proposal, approve_plan, plan_undo,
)

proposal = decode_proposal_json(untrusted_model_json_bytes)
plan = validate_proposal(
    proposal, task=trusted_card, revision=current_state_revision,
    opt_in=True, can_edit=True,
    project_grants=("project-1",),
    priorities=("low", "medium", "high"),
    budget={"perProposalMaxCredits": 150, "remainingCredits": 200,
            "maxTotalTokens": 3000},
    now="2026-10-21T12:00:00Z",
)
# Show plan.changes, plan.provenance, plan.estimated_credits and plan.digest.
# A preview alone does not permit saving.

intent = approve_plan(
    plan, task=latest_trusted_card, revision=current_state_revision,
    approval={"decision": "approve", "planDigest": plan.digest,
              "reviewer": "manager-1", "approvalId": "approval-unique-id"},
    reviewer="manager-1", opt_in=True, can_edit=True,
    project_grants=("project-1",), budget=latest_budget,
    now="2026-10-21T12:01:00Z",
)
# intent.candidate_task is an independent deepcopy with only allowed edits.
# intent.receipt, intent.audit, intent.budget_remaining_credits are intents:
# no charge, audit or task save has occurred yet.
```

The `ChangePlan` and every `FieldDiff` are immutable frozen dataclasses;
the ordered diff contains each field's original and proposed values.
`plan.digest` is a deterministic SHA-256 commitment to the task's **full**
snapshot hash, source revision, provenance and usage. It protects against
accidental changed preview contents, **not a cryptographic human signature**.
Revisions are 64 lowercase hex characters, matching the integration router's
current revision form. The caller must supply revision and full trusted card
from one consistent snapshot. Both are rechecked at approval, including
financial data changed concurrently despite being outside the edit allowlist.

`opt_in is True`, `can_edit is True`, and explicit project grants are
required at preview, approval, and undo planning. These are **trusted host
arguments**, not fields from model output. The caller must establish the
reviewer's authenticated identity and permissions afresh. Approval accepts only
an exact, explicit `decision="approve"`, matching plan digest and reviewer ID.
Plans over 24 hours old, changed task snapshots, rev conflicts, invalid
metadata, and budget changes all block approval.

The `usage` and `budget` unit is an application-defined integer **credit**
unit, not a currency amount. Preview and approval enforce per-proposal,
remaining-credit and total-token caps. The host must derive actual model usage
and reconcile charges from the provider using a separate accounting policy;
the AI's own estimated figures cannot enforce an external billing cap.
The core never calls a provider or charges a wallet.

## Mandatory host integration gates

1. **Opt-in and provenance:** explicitly enable AI for the authenticated
   account and project; pass only permitted nonfinancial card projection to
   the model; record request hash, model/provider from the host's observed
   invocation and accessible source IDs. Decode bounded model output using
   `decode_proposal_json` before validation.
2. **Inspectable review:** display before/after field diff, task ID/project,
   provenance, estimated tokens/credits and digest in a confirmation UI.
   Disabling, canceling, dismissing, or changing the proposal means no write.
   Require a fresh human approval tied to the displayed digest.
3. **Authoritative checks:** inside one host transaction/lock, re-resolve
   role, active account/session, project grants, task, authoritative state
   revision and full task digest. Recheck budget and whether `approvalId`
   has already been committed; duplicate ID with a different plan must
   conflict, exact replay must not charge or edit twice.
4. **Atomic commit:** call `approve_plan` to get the pure `ApprovalIntent`.
   Compare `receipt.planned_task_sha256` to the final candidate task digest
   before committing. CAS-write only the allowed task fields while preserving
   every other field; consume budget and append immutable audit and approval
   receipt in the **same transaction**. Do not dispatch automation, invoice,
   accounting, rule, or arbitrary network/file side effects. If host storage
   cannot commit all four domains together, do not enable M-10 apply.
5. **Audit/replay:** append approval and rejection events with actor,
   timestamps, changes, revision, provenance and estimated/actual usage as
   appropriate; sensitive data must remain ACL protected. The returned
   `intent.audit` is a proposal to log, not proof anything was persisted.
   Give each persisted approval a unique ID with durable idempotency guard.
6. **Undo:** after the host verifies that `ApprovalReceipt` was persisted
   and its task result and new committed revision are authoritative, call
   `plan_undo(receipt, committed_revision=..., task=..., revision=...,
   persisted=True, opt_in=True, can_edit=True, project_grants=...)`.
   This yields an immutable reverse `UndoPlan` only if the **entire current
   task snapshot** still matches the approved outcome. Show it in a second
   human-review flow and require new approval, new CAS, idempotency, budget/
   audit policy and atomic persistence. The returned plan never performs a
   rollback and does not itself authorize a reversal.

The host must not confuse `intent.candidate_task` (a mutable copy returned
for applying after validation) with the immutable diff. The host should verify
the candidate digest and revalidate the target state inside its critical
section, then commit only allowed fields. SHA-256 equality is a concurrency
check and change-content commitment, not user authentication or an ACL.

## Evidence and exclusions

`python -m unittest discover -s tests -p test_ai_change_review.py -v`
completed **20 synthetic tests, all PASS (2026-10-21)**. Cases exercise
strict JSON decoding, snapshots, allowlists, opt-in, reviewer identity,
budget/usage types and caps, provenance and time validity, CAS/full task
snapshot, immutable diff, no private-field mutation, and non-executing undo
plans. Unit tests do **not** simulate the provider, durable idempotency journal,
actual account/ACL service, native database transaction, LAN, EXE, publishing
or external billing. None of those acceptance gates is claimed complete.
