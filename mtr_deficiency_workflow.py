"""E3 pure metadata-only deficiency workflow, Refine 6.6-6.8 / AC-08..10.

No file, network, official Taraz API, ledger or persistence access. Inputs
(identity, project grants, receipt verification and saved baseline) MUST be
supplied by a trusted, authenticated server adapter, never by client flags.
The returned manual send intent is NOT a send, receipt, or finance approval.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
import re
from typing import Mapping


class DeficiencyError(ValueError):
    """Invalid evidence, stale data, wrong state or replay attempt."""


_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_FINANCE_ROLE = "taraz_finance_reviewer"
_REFER = "finance_deficiency_refer"
_RESOLVE = "deficiency_resolve"
_SUBMIT = "finance_request_resubmit"


def _text(name: str, value: str, *, max_length: int = 256) -> str:
    if (not isinstance(value, str) or not value or len(value) > max_length
            or value != value.strip() or not value.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise DeficiencyError(f"invalid {name}")
    return value


def _time(name: str, value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise DeficiencyError(f"{name} requires timezone-aware datetime")
    return value


def _positive(name: str, value: int) -> int:
    if type(value) is not int or value < 1:
        raise DeficiencyError(f"invalid {name}")
    return value


def _set(name: str, value: frozenset[str]) -> frozenset[str]:
    if not isinstance(value, frozenset):
        raise DeficiencyError(f"{name} must be frozenset")
    for item in value:
        _text(name + " item", item)
    return value


@dataclass(frozen=True, slots=True)
class Principal:
    """Trusted server snapshot, not a user-supplied claim of privilege."""

    user_id: str
    org_id: str
    role: str
    projects: frozenset[str]
    capabilities: frozenset[str]
    authenticated: bool
    active: bool = True

    def __post_init__(self) -> None:
        _text("user_id", self.user_id)
        _text("org_id", self.org_id)
        _text("role", self.role)
        _set("projects", self.projects)
        _set("capabilities", self.capabilities)
        if type(self.authenticated) is not bool or type(self.active) is not bool:
            raise DeficiencyError("auth and active must be explicit booleans")


@dataclass(frozen=True, slots=True)
class Baseline:
    """Server-saved request revision and raw/canonical payload fingerprint."""

    request_id: str
    org_id: str
    project_id: str
    revision: int
    digest: str

    def __post_init__(self) -> None:
        for key in ("request_id", "org_id", "project_id"):
            _text(key, getattr(self, key))
        _positive("revision", self.revision)
        if not isinstance(self.digest, str) or not _DIGEST.fullmatch(self.digest):
            raise DeficiencyError("baseline requires SHA-256 hex digest")


@dataclass(frozen=True, slots=True)
class FinanceReceipt:
    """Trusted adapter's receipt evidence, NOT self-verifying proof."""

    receipt_id: str
    request_id: str
    org_id: str
    project_id: str
    revision: int
    digest: str
    generation: int
    status: str
    source: str
    verified_by_adapter: bool
    occurred_at: datetime

    def __post_init__(self) -> None:
        for key in ("receipt_id", "request_id", "org_id", "project_id", "source", "status"):
            _text(key, getattr(self, key))
        _positive("revision", self.revision)
        _positive("generation", self.generation)
        if not isinstance(self.digest, str) or not _DIGEST.fullmatch(self.digest):
            raise DeficiencyError("invalid receipt digest")
        _time("receipt occurred_at", self.occurred_at)
        if type(self.verified_by_adapter) is not bool:
            raise DeficiencyError("receipt verification must be an explicit boolean")


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event_id: str
    actor_id: str
    action: str
    occurred_at: datetime
    details: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        _text("event_id", self.event_id)
        _text("actor_id", self.actor_id)
        _text("action", self.action)
        _time("event occurred_at", self.occurred_at)
        if not isinstance(self.details, tuple):
            raise DeficiencyError("audit details must be immutable")
        for item in self.details:
            if not isinstance(item, tuple) or len(item) != 2:
                raise DeficiencyError("invalid audit detail")
            _text("audit detail key", item[0])
            _text("audit detail value", item[1], max_length=1000)


@dataclass(frozen=True, slots=True)
class ReviewCase:
    baseline: Baseline
    expected_receipt_id: str
    expected_receipt_generation: int
    previous_receipt_ids: frozenset[str] = frozenset()
    previous_send_keys: frozenset[str] = frozenset()
    review_state: str = "IN_FINANCE_REVIEW"
    audit: tuple[AuditEvent, ...] = ()

    def __post_init__(self) -> None:
        if type(self.baseline) is not Baseline:
            raise DeficiencyError("baseline must be a saved request snapshot")
        _text("expected_receipt_id", self.expected_receipt_id)
        _positive("expected_receipt_generation", self.expected_receipt_generation)
        _set("previous_receipt_ids", self.previous_receipt_ids)
        _set("previous_send_keys", self.previous_send_keys)
        if self.review_state not in {"IN_FINANCE_REVIEW", "AWAITING_FINANCE_REVIEW"}:
            raise DeficiencyError("invalid finance review state")
        if not isinstance(self.audit, tuple) or not all(type(x) is AuditEvent for x in self.audit):
            raise DeficiencyError("invalid audit history")
        if len({x.event_id for x in self.audit}) != len(self.audit):
            raise DeficiencyError("duplicate audit event")


@dataclass(frozen=True, slots=True)
class AssignedDeficiency:
    review: ReviewCase
    receipt: FinanceReceipt
    reviewer_id: str
    assignee_id: str
    deadline: datetime
    reason: str
    missing_fields: frozenset[str]
    audit: tuple[AuditEvent, ...]
    state: str = field(default="DEFICIENCY_ASSIGNED", init=False)


@dataclass(frozen=True, slots=True)
class ReadyForManualResubmission:
    assigned: AssignedDeficiency
    corrected_baseline: Baseline
    corrections: tuple[tuple[str, str], ...]
    resolution_note: str
    remaining_missing_fields: frozenset[str]
    audit: tuple[AuditEvent, ...]
    state: str = field(default="CORRECTED_READY_FOR_RESUBMIT", init=False)


@dataclass(frozen=True, slots=True)
class ManualResubmissionIntent:
    """A purely in-memory permission decision; NO transport or posting."""

    ready: ReadyForManualResubmission
    authorized_actor_id: str
    new_send_key: str
    audit: tuple[AuditEvent, ...]
    state: str = field(default="MANUAL_RESUBMISSION_INTENT_ONLY", init=False)
    sent_to_taraz: bool = field(default=False, init=False)
    financial_event_created: bool = field(default=False, init=False)


def _scope(principal: Principal, baseline: Baseline, capability: str, *, acting: bool) -> None:
    if type(principal) is not Principal:
        raise PermissionError("trusted principal required")
    if principal.org_id != baseline.org_id or baseline.project_id not in principal.projects:
        raise PermissionError("organization or project access denied")
    if not principal.active or capability not in principal.capabilities:
        raise PermissionError("capability denied")
    if acting and principal.authenticated is not True:
        raise PermissionError("authenticated user required")


def _event(
    audit: tuple[AuditEvent, ...],
    *,
    event_id: str,
    actor: Principal,
    action: str,
    when: datetime,
    details: tuple[tuple[str, str], ...],
) -> tuple[AuditEvent, ...]:
    _text("event_id", event_id)
    _time("occurred_at", when)
    if any(existing.event_id == event_id for existing in audit):
        raise DeficiencyError("duplicate audit event")
    if audit and when < audit[-1].occurred_at:
        raise DeficiencyError("audit time predates previous event")
    return audit + (AuditEvent(event_id, actor.user_id, action, when, details),)


def refer_deficiency(
    case: ReviewCase,
    receipt: FinanceReceipt,
    *,
    reviewer: Principal,
    assignee: Principal,
    deadline: datetime,
    reason: str,
    missing_fields: frozenset[str],
    event_id: str,
    occurred_at: datetime,
) -> AssignedDeficiency:
    """Only a finance reviewer can refer a *verified* deficiency to a scoped assignee."""
    if type(case) is not ReviewCase or type(receipt) is not FinanceReceipt:
        raise DeficiencyError("finance review case and receipt required")
    base = case.baseline
    _scope(reviewer, base, _REFER, acting=True)
    if reviewer.role != _FINANCE_ROLE:
        raise PermissionError("only a Taraz finance reviewer can refer deficiencies")
    _scope(assignee, base, _RESOLVE, acting=False)
    if case.review_state != "IN_FINANCE_REVIEW":
        raise DeficiencyError("finance review is still pending")
    if (receipt.source != "taraz" or receipt.verified_by_adapter is not True
            or receipt.status != "deficiency_required"):
        raise DeficiencyError("verified Taraz deficiency receipt required")
    if (receipt.receipt_id != case.expected_receipt_id
            or receipt.receipt_id in case.previous_receipt_ids
            or receipt.generation != case.expected_receipt_generation):
        raise DeficiencyError("duplicate, stale or unexpected finance receipt")
    if (
        (receipt.request_id, receipt.org_id, receipt.project_id,
         receipt.revision, receipt.digest)
        != (base.request_id, base.org_id, base.project_id, base.revision, base.digest)
    ):
        raise DeficiencyError("receipt does not match request identity and revision")
    _time("occurred_at", occurred_at)
    _time("deadline", deadline)
    if receipt.occurred_at > occurred_at or deadline <= occurred_at:
        raise DeficiencyError("receipt time or assignee deadline is inconsistent")
    _text("reason", reason, max_length=1000)
    _set("missing_fields", missing_fields)
    if not missing_fields:
        raise DeficiencyError("at least one missing field must be identified")
    audit = _event(
        case.audit, event_id=event_id, actor=reviewer,
        action="deficiency_referred", when=occurred_at,
        details=(
            ("receipt_id", receipt.receipt_id),
            ("assignee_id", assignee.user_id),
            ("deadline", deadline.isoformat()),
            ("reason", reason),
            ("missing_fields", ",".join(sorted(missing_fields))),
        ),
    )
    return AssignedDeficiency(
        review=replace(
            case, previous_receipt_ids=case.previous_receipt_ids | {receipt.receipt_id},
        ),
        receipt=receipt, reviewer_id=reviewer.user_id,
        assignee_id=assignee.user_id, deadline=deadline,
        reason=reason, missing_fields=missing_fields, audit=audit,
    )


def resolve_deficiency(
    assigned: AssignedDeficiency,
    *,
    actor: Principal,
    corrections: Mapping[str, str],
    result_note: str,
    saved_baseline: Baseline,
    event_id: str,
    occurred_at: datetime,
) -> ReadyForManualResubmission:
    """Record assignee's resolution without sending anything back to Taraz."""
    if type(assigned) is not AssignedDeficiency:
        raise DeficiencyError("deficiency must first be assigned by finance")
    original = assigned.review.baseline
    _scope(actor, original, _RESOLVE, acting=True)
    if actor.user_id != assigned.assignee_id:
        raise PermissionError("only the assigned user can resolve this deficiency")
    if type(saved_baseline) is not Baseline:
        raise DeficiencyError("new server-saved baseline required")
    if (saved_baseline.request_id, saved_baseline.org_id, saved_baseline.project_id) != (
        original.request_id, original.org_id, original.project_id
    ):
        raise DeficiencyError("saved baseline belongs to a different case")
    if saved_baseline.revision <= original.revision or saved_baseline.digest == original.digest:
        raise DeficiencyError("resolution requires a changed newer saved baseline")
    if not isinstance(corrections, Mapping) or not corrections:
        raise DeficiencyError("at least one correction is required")
    changes: list[tuple[str, str]] = []
    for name, value in corrections.items():
        _text("corrected field", name)
        _text("corrected value", value, max_length=1000)
        if name not in assigned.missing_fields:
            raise DeficiencyError("correction not part of assigned missing fields")
        changes.append((name, value))
    _text("result_note", result_note, max_length=1000)
    changes.sort()
    _time("occurred_at", occurred_at)
    if occurred_at < assigned.audit[-1].occurred_at:
        raise DeficiencyError("resolution predates assignment")
    remaining = assigned.missing_fields - frozenset(corrections)
    audit = _event(
        assigned.audit, event_id=event_id, actor=actor,
        action="deficiency_corrected_ready_only", when=occurred_at,
        details=(
            ("fields", ",".join(field for field, _ in changes)),
            ("result", result_note),
            ("saved_revision", str(saved_baseline.revision)),
            ("remaining_missing", ",".join(sorted(remaining)) if remaining else "none"),
        ),
    )
    return ReadyForManualResubmission(
        assigned=assigned, corrected_baseline=saved_baseline,
        corrections=tuple(changes), resolution_note=result_note,
        remaining_missing_fields=remaining, audit=audit,
    )


def authorize_manual_resubmission(
    ready: ReadyForManualResubmission,
    *,
    actor: Principal,
    explicit_manual_action: bool,
    current_server_baseline: Baseline,
    server_revalidated: bool,
    new_send_key: str,
    warning_acknowledged: bool,
    event_id: str,
    occurred_at: datetime,
) -> ManualResubmissionIntent:
    """Return an intent only, never invoke a transport, ledger or official API.

    The caller must compare current_server_baseline atomically with its trusted
    store at the actual send boundary. server_revalidated is an *assertion by
    that trusted adapter*, not proof of such atomicity on its own.
    """
    if type(ready) is not ReadyForManualResubmission:
        raise DeficiencyError("deficiency is not corrected and ready")
    base = ready.assigned.review.baseline
    _scope(actor, base, _SUBMIT, acting=True)
    if explicit_manual_action is not True:
        raise PermissionError("explicit manual resubmission required")
    if server_revalidated is not True:
        raise DeficiencyError("fresh trusted server comparison required")
    if type(current_server_baseline) is not Baseline:
        raise DeficiencyError("current server baseline required")
    if current_server_baseline != ready.corrected_baseline:
        raise DeficiencyError("stale, changed or mismatched current baseline")
    if ready.remaining_missing_fields and warning_acknowledged is not True:
        raise DeficiencyError("incomplete business data requires visible warning acknowledgment")
    _text("new_send_key", new_send_key)
    if new_send_key in ready.assigned.review.previous_send_keys:
        raise DeficiencyError("resubmission must not reuse an already-used send key")
    _time("occurred_at", occurred_at)
    if occurred_at < ready.audit[-1].occurred_at:
        raise DeficiencyError("resubmission predates correction")
    audit = _event(
        ready.audit, event_id=event_id, actor=actor,
        action="manual_resubmission_intent_only", when=occurred_at,
        details=(
            ("new_send_key", new_send_key),
            ("baseline_revision", str(current_server_baseline.revision)),
            ("incomplete_warning_acknowledged",
             "yes" if ready.remaining_missing_fields else "not_required"),
        ),
    )
    return ManualResubmissionIntent(
        ready=ready, authorized_actor_id=actor.user_id,
        new_send_key=new_send_key, audit=audit,
    )
