"""Isolated, pure finance-workflow *design contract* for Madar/Taraz.

This module has no network, disk, financial-ledger, or external-app access. It
models a subset of user-approved Refine decisions with synthetic inputs and
returns decisions; nothing here sends a request or changes an official record.

Integration requires its own authorized design, ACL, backend revalidation,
idempotency, persistence, and acceptance testing. Do not load into production.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Mapping


class WorkflowContractError(ValueError):
    """A contract precondition or explicit approval is missing."""


class ConfirmationRequired(WorkflowContractError):
    """The authorized user must separately acknowledge a known warning."""


_MISSING = object()


def _required_id(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise WorkflowContractError(f"{name} must be a nonblank, trimmed string")
    return value


def _fields(name: str, values: Mapping[str, object]) -> Mapping[str, object]:
    if not isinstance(values, Mapping):
        raise WorkflowContractError(f"{name} must be a mapping")
    result = {}
    for key, value in values.items():
        _required_id(f"{name} field", key)
        result[key] = value
    return MappingProxyType(result)


@dataclass(frozen=True)
class AmendmentDraft:
    """An independent *draft*, not a financial request sent to Taraz.

    baseline is a snapshot of every field whose current value can affect this
    proposal. A caller must include dependencies; this pure module cannot
    discover field dependencies from an operational database.
    """

    amendment_id: str
    original_request_id: str
    proposed_fields: Mapping[str, object]
    baseline: Mapping[str, object]
    conflicting_fields: frozenset[str]
    resolutions: Mapping[str, object]
    created_by: str
    previous_rejected_amendment_id: str | None = None

    def __post_init__(self) -> None:
        _required_id("amendment_id", self.amendment_id)
        _required_id("original_request_id", self.original_request_id)
        _required_id("created_by", self.created_by)
        if self.amendment_id == self.original_request_id:
            raise WorkflowContractError("an amendment must not reuse the original ID")
        if self.previous_rejected_amendment_id is not None:
            _required_id("previous_rejected_amendment_id", self.previous_rejected_amendment_id)
            if self.previous_rejected_amendment_id in {self.amendment_id, self.original_request_id}:
                raise WorkflowContractError("invalid rejected amendment reference")
        proposed = _fields("proposed_fields", self.proposed_fields)
        baseline = _fields("baseline", self.baseline)
        resolutions = _fields("resolutions", self.resolutions)
        if not proposed or not set(proposed).issubset(baseline):
            raise WorkflowContractError("each proposed field needs a baseline value")
        if not isinstance(self.conflicting_fields, frozenset) or not all(
            isinstance(field, str) and bool(field) for field in self.conflicting_fields
        ):
            raise WorkflowContractError("conflicting_fields must be a frozenset of names")
        if not self.conflicting_fields.issubset(proposed):
            raise WorkflowContractError("conflict must refer to a proposed field")
        if not set(resolutions).issubset(self.conflicting_fields):
            raise WorkflowContractError("resolutions must refer to declared conflicts")
        object.__setattr__(self, "proposed_fields", proposed)
        object.__setattr__(self, "baseline", baseline)
        object.__setattr__(self, "resolutions", resolutions)


@dataclass(frozen=True)
class SubmissionDecision:
    """No side effects. allowed=True is not permission to send automatically."""

    allowed: bool
    blocked_by: tuple[str, ...]
    affected_fields_to_review: tuple[str, ...]


def create_amendment_draft(
    *,
    amendment_id: str,
    original_request_id: str,
    created_by: str,
    authorized: bool,
    proposed_fields: Mapping[str, object],
    baseline: Mapping[str, object],
    conflicting_fields: frozenset[str] = frozenset(),
    open_amendment_exists: bool = False,
    acknowledged_open_amendment: bool = False,
    similar_amendment_exists: bool = False,
    acknowledged_similar_amendment: bool = False,
    previous_rejected_amendment_id: str | None = None,
) -> AmendmentDraft:
    """Create independent draft after distinct required confirmations.

    This is a synthetic model of Refine 6.18/6.19/6.27, not a database insert.
    """

    if authorized is not True:
        raise PermissionError("authorized user required to create an amendment")
    if open_amendment_exists and acknowledged_open_amendment is not True:
        raise ConfirmationRequired("open amendment warning needs explicit acknowledgment")
    if similar_amendment_exists and acknowledged_similar_amendment is not True:
        raise ConfirmationRequired("possible duplicate needs separate acknowledgment")
    return AmendmentDraft(
        amendment_id=amendment_id,
        original_request_id=original_request_id,
        created_by=created_by,
        proposed_fields=proposed_fields,
        baseline=baseline,
        conflicting_fields=conflicting_fields,
        resolutions={},
        previous_rejected_amendment_id=previous_rejected_amendment_id,
    )


def resolve_conflict_fields(
    draft: AmendmentDraft,
    *,
    authorized: bool,
    chosen_values: Mapping[str, object],
) -> AmendmentDraft:
    """Return a new reviewed draft, leaving old draft/history untouched.

    The caller must separately persist actor/time/source in an audit event.
    """

    if authorized is not True:
        raise PermissionError("authorized reviewer required")
    choices = _fields("chosen_values", chosen_values)
    if not choices or not set(choices).issubset(draft.conflicting_fields):
        raise WorkflowContractError("only declared conflicting fields can be resolved")
    result = dict(draft.resolutions)
    result.update(choices)
    return replace(draft, resolutions=result, proposed_fields={**draft.proposed_fields, **choices})


def evaluate_manual_submission(
    draft: AmendmentDraft,
    *,
    authorized: bool,
    explicit_manual_action: bool,
    current_baseline: Mapping[str, object],
) -> SubmissionDecision:
    """Revalidate current inputs; return a decision only, never transmit.

    Any changed dependent field, including a now-missing one, requires fresh
    human review of *that* affected field. Unchanged dependencies do not get
    reopened. A production adapter must compare atomically at the server.
    """

    current = _fields("current_baseline", current_baseline)
    stale = tuple(sorted(
        field for field, previous in draft.baseline.items()
        if current.get(field, _MISSING) != previous
    ))
    unresolved = draft.conflicting_fields - set(draft.resolutions)
    blockers = []
    if authorized is not True:
        blockers.append("not_authorized")
    if explicit_manual_action is not True:
        blockers.append("manual_send_action_required")
    if unresolved:
        blockers.append("unresolved_field_conflicts")
    if stale:
        blockers.append("stale_baseline_requires_review")
    return SubmissionDecision(
        allowed=not blockers,
        blocked_by=tuple(blockers),
        affected_fields_to_review=stale,
    )


def recovery_action(
    *,
    receipt_state: str,
    original_send_authorized: bool,
    same_request_and_payload: bool,
    same_idempotency_key: bool,
) -> str:
    """Choose an offline policy for a *previous* authorized send (6.10).

    Returns one of: hold_no_approval, recover_receipt, replay_same_send,
    hold_mismatched_request, hold_uncertain. Never sends or queries Taraz.
    """

    if receipt_state not in {"received", "not_received", "unknown"}:
        raise WorkflowContractError("receipt_state must be received/not_received/unknown")
    if original_send_authorized is not True:
        return "hold_no_approval"
    if same_request_and_payload is not True or same_idempotency_key is not True:
        return "hold_mismatched_request"
    if receipt_state == "received":
        return "recover_receipt"
    if receipt_state == "not_received":
        return "replay_same_send"
    return "hold_uncertain"
