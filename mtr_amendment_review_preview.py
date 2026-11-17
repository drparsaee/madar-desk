"""Isolated E5 amendment-review PREVIEW for Madar ↔ Taraz (Refine 6.17–6.25, 6.27).

No filesystem, clock, network, state mutation, finance posting, automatic send,
or Taraz invocation. All inputs in this pilot are synthetic; the caller is
responsible for supplying a HOST-authenticated principal, same-organization
and project-scoped records, a verified Taraz rejection receipt, and timestamps.
The host must perform an atomic baseline/version check at any future real send.

This layer uses the existing mtr_finance_workflow_contract public API without
changing it. It adds explicit organization scoping, an independent related
request history, distinct warning acknowledgements, explainable per-field
conflicts, review events, and trustworthy rejection-field suggestions.

Proposed input shape:
  principal = {"userId":"editor", "orgId":"org-1", "projectIds":["project-1"],
               "canDraft":True, "canReview":True, "canSubmit":True}
  original = {"requestId":"req-1", "orgId":"org-1", "projectId":"project-1",
              "submitted":True, "revision":"rev-1",
              "fields":{"partyId":"old", "quantity":10}}
  related = [{"amendmentId":"am-1", "originalRequestId":"req-1",
              "orgId":"org-1", "projectId":"project-1", "revision":"r1",
              "status":"in_review", "proposedFields":{"partyId":"new"}}]

Only already-authorized related records may be supplied by the caller. This
pilot filters out other-organization and other-project records as a secondary
data minimization measure. It does not authenticate a user or discover related
records and never changes original requests, prior amendments or ledgers.

Duplicate detection is deliberately conservative: *identical* proposed field
payloads are flagged as potentially duplicate. Fuzzy thresholds are not
defined in the decisions and are not fabricated here. A trusted rejection
reason must include explicit affected field names: free text alone is NEVER
converted to a field assignment or an inferred correction.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
import re
from types import MappingProxyType
from typing import Mapping, Sequence

from mtr_finance_workflow_contract import (
    AmendmentDraft, WorkflowContractError, create_amendment_draft,
    evaluate_manual_submission, resolve_conflict_fields,
)


_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z", re.ASCII)
_FIELD = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}\Z", re.ASCII)
_OPEN = frozenset(("draft", "pending", "in_review"))
_STATUSES = _OPEN | {"rejected", "approved", "closed"}
_ABSENT = object()


class AmendmentPreviewError(ValueError):
    """Safe, identifier-free code for a rejected input or access attempt."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise AmendmentPreviewError(code)


def _exact(value: object, keys: tuple[str, ...], code: str) -> dict:
    _require(type(value) is dict and set(value) == set(keys), code)
    return value


def _id(value: object, code: str = "invalid_input") -> str:
    _require(type(value) is str and _ID.fullmatch(value) is not None, code)
    return value


def _fields(value: object) -> Mapping[str, object]:
    _require(type(value) is dict and 0 < len(value) <= 48, "invalid_fields")
    result = {}
    for field, item in value.items():
        _require(type(field) is str and _FIELD.fullmatch(field) is not None,
                 "invalid_fields")
        # Restrict this preview to bounded immutable scalar values. No
        # nested finance objects or mutable caller-owned payloads are retained.
        _require(type(item) in (str, int, bool, type(None)), "invalid_fields")
        if type(item) is str:
            _require(len(item) <= 240 and not any(ord(ch) < 32 for ch in item),
                     "invalid_fields")
        if type(item) is int:
            _require(abs(item) <= 10**15, "invalid_fields")
        result[field] = item
    return MappingProxyType(result)


def _same(a: object, b: object) -> bool:
    return type(a) is type(b) and a == b


def _same_fields(a: Mapping, b: Mapping) -> bool:
    return set(a) == set(b) and all(_same(a[k], b[k]) for k in a)


def _time(value: object) -> str:
    _require(type(value) is str and 10 <= len(value) <= 40 and "T" in value,
             "invalid_time")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AmendmentPreviewError("invalid_time") from exc
    _require(dt.tzinfo is not None and dt.utcoffset() is not None,
             "invalid_time")
    return value


def _principal(value: object) -> dict:
    p = _exact(value, ("userId", "orgId", "projectIds", "canDraft",
                       "canReview", "canSubmit"), "invalid_principal")
    _id(p["userId"], "invalid_principal")
    _id(p["orgId"], "invalid_principal")
    grants = p["projectIds"]
    _require(type(grants) is list and len(grants) <= 1000,
             "invalid_principal")
    _require(all(type(x) is str and _ID.fullmatch(x) for x in grants) and
             len(grants) == len(set(grants)), "invalid_principal")
    _require(all(type(p[key]) is bool for key in
                 ("canDraft", "canReview", "canSubmit")), "invalid_principal")
    return p


def _authorize(principal: object, org: str, project: str, permission: str) -> str:
    p = _principal(principal)
    # Same code on organization mismatch, absent project or denied action.
    # Foreign object identifiers are never included in exception messages.
    _require(p["orgId"] == org and project in p["projectIds"] and
             p[permission] is True, "scope_denied")
    return p["userId"]


def _original(value: object) -> dict:
    item = _exact(value, ("requestId", "orgId", "projectId", "submitted",
                          "revision", "fields"), "invalid_original")
    for key in ("requestId", "orgId", "projectId", "revision"):
        _id(item[key], "invalid_original")
    _require(type(item["submitted"]) is bool, "invalid_original")
    return {**item, "fields": _fields(item["fields"])}


def _related(value: object, *, org: str, project: str,
             original_id: str) -> tuple[dict, ...]:
    _require(type(value) in (list, tuple) and len(value) <= 128,
             "invalid_related")
    result = []
    used = set()
    for raw in value:
        # Only tenant-scoped references are inspected beyond these fields.
        # Host filtering is still mandatory. Cross-tenant data are ignored
        # without leaking IDs, values, or validation errors from their body.
        if type(raw) is not dict or raw.get("orgId") != org or raw.get("projectId") != project:
            continue
        item = _exact(raw, ("amendmentId", "originalRequestId", "orgId",
                            "projectId", "revision", "status",
                            "proposedFields"), "invalid_related")
        for key in ("amendmentId", "originalRequestId", "revision"):
            _id(item[key], "invalid_related")
        if item["originalRequestId"] != original_id:
            continue
        _require(type(item["status"]) is str and
                 item["status"] in _STATUSES, "invalid_related")
        _require(item["amendmentId"] not in used and
                 item["amendmentId"] != original_id, "invalid_related")
        used.add(item["amendmentId"])
        result.append({**item, "proposedFields": _fields(item["proposedFields"])})
    return tuple(result)


@dataclass(frozen=True)
class FieldConflict:
    field: str
    baseline_value: object
    proposed_value: object
    related_amendment_id: str
    related_value: object
    related_revision: str


@dataclass(frozen=True)
class ReviewEvent:
    user_id: str
    occurred_at: str
    kind: str
    choices: tuple[tuple[str, object], ...]
    source_amendment_ids: tuple[str, ...]


@dataclass(frozen=True)
class RelatedSnapshot:
    amendment_id: str
    revision: str
    proposed_fields: Mapping[str, object]


@dataclass(frozen=True)
class ScopedAmendmentDraft:
    """Independent candidate draft. Contains no reference to mutable inputs."""

    org_id: str
    project_id: str
    original_revision: str
    contract: AmendmentDraft
    conflicts: tuple[FieldConflict, ...]
    related_snapshots: tuple[RelatedSnapshot, ...]
    review_events: tuple[ReviewEvent, ...]
    status: str = "draft"


@dataclass(frozen=True)
class CreationPreview:
    allowed: bool
    blocked_by: tuple[str, ...]
    open_amendment_ids: tuple[str, ...]
    possible_duplicate_ids: tuple[str, ...]
    draft: ScopedAmendmentDraft | None
    action: str = "preview_only"


@dataclass(frozen=True)
class SubmissionPreview:
    """allowed=True permits only a future separately authorized manual send."""

    allowed: bool
    blocked_by: tuple[str, ...]
    affected_fields_to_review: tuple[str, ...]
    unresolved_conflict_fields: tuple[str, ...]
    action: str = "preview_only"


@dataclass(frozen=True)
class RejectionFieldSuggestion:
    field: str
    rejected_previous_value: object
    rejected_proposed_value: object
    suggested_value: None = None  # Human must choose; no inferred correction.


@dataclass(frozen=True)
class RejectionGuidance:
    original_request_id: str
    rejected_amendment_id: str
    reason_status: str
    reason_text: str | None
    suggested_fields: tuple[RejectionFieldSuggestion, ...]
    next_actions: tuple[str, ...]
    action: str = "preview_only"


def preview_create_amendment(
    *, principal: dict, original: dict, amendment_id: str,
    proposed_fields: dict, related_amendments: Sequence[dict] = (),
    acknowledged_open: bool = False, acknowledged_duplicate: bool = False,
    acknowledged_at: str | None = None,
    previous_rejected_amendment_id: str | None = None,
) -> CreationPreview:
    """Create only an in-memory candidate after two *distinct* acknowledgments.

    Open warnings (6.19) and possible duplicate warnings (6.27) are separately
    derived from authorized related amendments. This function never persists.
    """
    # Scope before inspecting private field values, including malformed data.
    _require(type(original) is dict, "invalid_original")
    actor = _authorize(principal, original.get("orgId"),
                       original.get("projectId"), "canDraft")
    base = _original(original)
    _require(base["submitted"] is True, "original_not_submitted")
    _id(amendment_id)
    _require(amendment_id != base["requestId"], "invalid_amendment_id")
    _require(type(acknowledged_open) is bool and
             type(acknowledged_duplicate) is bool, "invalid_acknowledgment")
    proposed = _fields(proposed_fields)
    _require(set(proposed).issubset(base["fields"]), "missing_baseline_fields")
    related = _related(related_amendments, org=base["orgId"],
                       project=base["projectId"],
                       original_id=base["requestId"])
    _require(amendment_id not in {r["amendmentId"] for r in related},
             "amendment_id_already_exists")
    if previous_rejected_amendment_id is not None:
        _id(previous_rejected_amendment_id)
        _require(any(r["amendmentId"] == previous_rejected_amendment_id and
                     r["status"] == "rejected" for r in related),
                 "rejected_reference_not_available")
    open_ids = tuple(sorted(r["amendmentId"] for r in related
                            if r["status"] in _OPEN))
    duplicate_ids = tuple(sorted(r["amendmentId"] for r in related
                                 if _same_fields(r["proposedFields"], proposed)))
    blockers = []
    if open_ids and not acknowledged_open:
        blockers.append("open_amendment_ack_required")
    if duplicate_ids and not acknowledged_duplicate:
        blockers.append("possible_duplicate_ack_required")
    if blockers:
        return CreationPreview(False, tuple(blockers), open_ids,
                               duplicate_ids, None)
    events = ()
    if (open_ids and acknowledged_open) or (duplicate_ids and acknowledged_duplicate):
        timestamp = _time(acknowledged_at)
        recorded = []
        if open_ids:
            recorded.append(ReviewEvent(
                actor, timestamp, "acknowledge_open_amendment", (), open_ids))
        if duplicate_ids:
            recorded.append(ReviewEvent(
                actor, timestamp, "acknowledge_possible_duplicate", (), duplicate_ids))
        events = tuple(recorded)
    conflicts = tuple(sorted((
        FieldConflict(field, base["fields"][field], proposed[field],
                      rel["amendmentId"], value, rel["revision"])
        for rel in related if rel["status"] in _OPEN
        for field, value in rel["proposedFields"].items()
        if field in proposed and not _same(value, proposed[field])
    ), key=lambda c: (c.field, c.related_amendment_id)))
    try:
        contract = create_amendment_draft(
            amendment_id=amendment_id, original_request_id=base["requestId"],
            created_by=actor, authorized=True, proposed_fields=dict(proposed),
            baseline=dict(base["fields"]),
            conflicting_fields=frozenset(c.field for c in conflicts),
            open_amendment_exists=bool(open_ids),
            acknowledged_open_amendment=acknowledged_open,
            similar_amendment_exists=bool(duplicate_ids),
            acknowledged_similar_amendment=acknowledged_duplicate,
            previous_rejected_amendment_id=previous_rejected_amendment_id,
        )
    except WorkflowContractError as exc:
        raise AmendmentPreviewError("invalid_amendment_draft") from exc
    scoped = ScopedAmendmentDraft(
        base["orgId"], base["projectId"], base["revision"], contract,
        conflicts,
        tuple(sorted((
            RelatedSnapshot(r["amendmentId"], r["revision"], r["proposedFields"])
            for r in related if r["status"] in _OPEN
        ), key=lambda snapshot: snapshot.amendment_id)), events,
    )
    return CreationPreview(True, (), open_ids, duplicate_ids, scoped)


def review_field_choices(
    draft: ScopedAmendmentDraft, *, principal: dict,
    chosen_values: dict, occurred_at: str,
) -> ScopedAmendmentDraft:
    """Return a new preview after an authorized, explicit field-by-field choice.

    The previous draft, unrelated proposals, and original stay untouched.
    Only fields flagged in the snapshot can be resolved. A host audit still
    has to persist and sign this event; no event is saved by this function.
    """
    _require(type(draft) is ScopedAmendmentDraft, "invalid_draft")
    actor = _authorize(principal, draft.org_id, draft.project_id, "canReview")
    timestamp = _time(occurred_at)
    selected = _fields(chosen_values)
    _require(set(selected).issubset(draft.contract.conflicting_fields),
             "unrelated_field_choice")
    try:
        updated = resolve_conflict_fields(
            draft.contract, authorized=True, chosen_values=dict(selected))
    except WorkflowContractError as exc:
        raise AmendmentPreviewError("invalid_field_choice") from exc
    refs = tuple(sorted({c.related_amendment_id for c in draft.conflicts
                         if c.field in selected}))
    event = ReviewEvent(actor, timestamp, "resolve_conflict",
                        tuple(sorted(selected.items())), refs)
    return replace(draft, contract=updated,
                   review_events=draft.review_events + (event,))


def _scope_original(draft: ScopedAmendmentDraft, candidate: object) -> None:
    _require(type(candidate) is dict and
             candidate.get("orgId") == draft.org_id and
             candidate.get("projectId") == draft.project_id and
             candidate.get("requestId") == draft.contract.original_request_id,
             "scope_denied")


def _changed_original_fields(draft: ScopedAmendmentDraft,
                             current: dict) -> set[str]:
    stale = set()
    for field in set(draft.contract.baseline) | set(current["fields"]):
        past = draft.contract.baseline.get(field, _ABSENT)
        present = current["fields"].get(field, _ABSENT)
        if past is _ABSENT or present is _ABSENT or not _same(past, present):
            stale.add(field)
    return stale


def _changed_related_fields(draft: ScopedAmendmentDraft,
                            related: tuple[dict, ...]) -> set[str]:
    old_related = {s.amendment_id: s for s in draft.related_snapshots}
    relevant = {r["amendmentId"]: r for r in related if r["status"] in _OPEN}
    changed = set()
    # Capture changes even if a caller fails to advance a related revision.
    for ident in set(old_related) | set(relevant):
        before, after = old_related.get(ident), relevant.get(ident)
        if before is None:
            affected = set(after["proposedFields"])
        elif after is None:
            affected = set(before.proposed_fields)
        elif (before.revision == after["revision"] and
              _same_fields(before.proposed_fields, after["proposedFields"])):
            continue
        else:
            affected = set(before.proposed_fields) | set(after["proposedFields"])
        changed.update(affected & set(draft.contract.proposed_fields))
    return changed


def preview_manual_submission(
    draft: ScopedAmendmentDraft, *, principal: dict, current_original: dict,
    current_related_amendments: Sequence[dict], explicit_manual_action: bool,
) -> SubmissionPreview:
    """Inspect blockers. Does not send to Taraz, update a request, or post.

    Requires fresh same-org/project snapshots. A changed original revision
    always blocks; only fields with changed current/baseline values are
    reopened. Related changes invalidate the affected overlapping decisions.
    Any eventual live send requires server-side atomic compare-and-submit.
    """
    _require(type(draft) is ScopedAmendmentDraft, "invalid_draft")
    _authorize(principal, draft.org_id, draft.project_id, "canSubmit")
    _require(type(explicit_manual_action) is bool, "invalid_manual_action")
    _scope_original(draft, current_original)
    current = _original(current_original)
    _require(current["submitted"] is True, "original_not_submitted")
    related = tuple(
        rel for rel in _related(current_related_amendments, org=draft.org_id,
                                project=draft.project_id,
                                original_id=draft.contract.original_request_id)
        if rel["amendmentId"] != draft.contract.amendment_id
    )
    old_related = {s.amendment_id: s for s in draft.related_snapshots}
    changed_related = _changed_related_fields(draft, related)
    stale = _changed_original_fields(draft, current)
    core = evaluate_manual_submission(
        draft.contract, authorized=True,
        explicit_manual_action=explicit_manual_action,
        current_baseline=dict(current["fields"]),
    )
    unresolved = set(draft.contract.conflicting_fields) - set(draft.contract.resolutions)
    # Any newly conflicting related proposal must also be actively decided;
    # no old consent can silently cover a new source.
    for item in related:
        if item["status"] in _OPEN:
            for field, value in item["proposedFields"].items():
                if (field in draft.contract.proposed_fields and
                        not _same(value, draft.contract.proposed_fields[field]) and
                        (item["amendmentId"] not in old_related or
                         item["revision"] != old_related[item["amendmentId"]].revision or
                         not _same_fields(item["proposedFields"],
                                          old_related[item["amendmentId"]].proposed_fields))):
                    unresolved.add(field)
    blockers = list(core.blocked_by)
    if current["revision"] != draft.original_revision:
        blockers.append("stale_original_revision")
    if changed_related:
        blockers.append("changed_related_amendment")
    if unresolved and "unresolved_field_conflicts" not in blockers:
        blockers.append("unresolved_field_conflicts")
    return SubmissionPreview(
        allowed=not blockers, blocked_by=tuple(dict.fromkeys(blockers)),
        affected_fields_to_review=tuple(sorted(stale | changed_related)),
        unresolved_conflict_fields=tuple(sorted(unresolved)),
    )


def review_changed_baseline(
    draft: ScopedAmendmentDraft, *, principal: dict, current_original: dict,
    current_related_amendments: Sequence[dict], chosen_values: dict,
    acknowledged_dependency_fields: list[str],
    acknowledged_revision_change: bool, occurred_at: str,
) -> ScopedAmendmentDraft:
    """Human re-reviews precisely affected stale fields, returning a NEW draft.

    An affected proposal field requires an explicit chosen value, even when
    retaining its old value. Changed dependencies outside the proposal require
    explicit acknowledgments instead. A revision change with no field delta
    still requires a distinct acknowledgment. No baseline is rebased silently.
    """
    _require(type(draft) is ScopedAmendmentDraft, "invalid_draft")
    actor = _authorize(principal, draft.org_id, draft.project_id, "canReview")
    timestamp = _time(occurred_at)
    _scope_original(draft, current_original)
    current = _original(current_original)
    _require(current["submitted"] is True, "original_not_submitted")
    related = tuple(
        rel for rel in _related(current_related_amendments, org=draft.org_id,
                                project=draft.project_id,
                                original_id=draft.contract.original_request_id)
        if rel["amendmentId"] != draft.contract.amendment_id
    )
    affected = _changed_original_fields(draft, current) | _changed_related_fields(draft, related)
    _require(affected or current["revision"] != draft.original_revision,
             "nothing_to_re_review")
    _require(type(acknowledged_revision_change) is bool,
             "invalid_acknowledgment")
    if current["revision"] != draft.original_revision:
        _require(acknowledged_revision_change, "revision_ack_required")
    _require(type(acknowledged_dependency_fields) is list and
             len(acknowledged_dependency_fields) <= 48 and
             all(type(field) is str and _FIELD.fullmatch(field)
                 for field in acknowledged_dependency_fields) and
             len(set(acknowledged_dependency_fields)) ==
             len(acknowledged_dependency_fields), "invalid_acknowledgment")
    expected_choice_fields = affected & set(draft.contract.proposed_fields)
    expected_dependency_fields = affected - set(draft.contract.proposed_fields)
    _require(set(acknowledged_dependency_fields) == expected_dependency_fields,
             "incomplete_dependency_review")
    _require(type(chosen_values) is dict and set(chosen_values) ==
             expected_choice_fields, "incomplete_field_review")
    # _fields normally requires a nonempty mapping; revision-only and
    # dependency-only reviews correctly allow no proposal choices.
    chosen = _fields(chosen_values) if chosen_values else MappingProxyType({})
    proposed = {**draft.contract.proposed_fields, **chosen}
    _require(set(proposed).issubset(current["fields"]),
             "missing_baseline_fields")
    conflicts = tuple(sorted((
        FieldConflict(field, current["fields"][field], proposed[field],
                      rel["amendmentId"], value, rel["revision"])
        for rel in related if rel["status"] in _OPEN
        for field, value in rel["proposedFields"].items()
        if field in proposed and not _same(value, proposed[field])
    ), key=lambda conflict: (conflict.field, conflict.related_amendment_id)))
    conflict_fields = frozenset(item.field for item in conflicts)
    resolutions = {
        field: value for field, value in draft.contract.resolutions.items()
        if field in conflict_fields and field not in affected
    }
    resolutions.update({field: value for field, value in chosen.items()
                        if field in conflict_fields})
    try:
        updated_contract = replace(
            draft.contract,
            proposed_fields=proposed, baseline=dict(current["fields"]),
            conflicting_fields=conflict_fields, resolutions=resolutions,
        )
    except WorkflowContractError as exc:
        raise AmendmentPreviewError("invalid_re_review") from exc
    event = ReviewEvent(
        actor, timestamp, "review_changed_baseline",
        tuple(sorted((*chosen.items(),
                      *((field, "dependency_acknowledged")
                        for field in expected_dependency_fields)))),
        tuple(sorted({s.amendment_id for s in draft.related_snapshots} |
                     {r["amendmentId"] for r in related if r["status"] in _OPEN})),
    )
    snapshots = tuple(sorted((
        RelatedSnapshot(rel["amendmentId"], rel["revision"],
                        rel["proposedFields"]) for rel in related
        if rel["status"] in _OPEN
    ), key=lambda item: item.amendment_id))
    return replace(
        draft, original_revision=current["revision"],
        contract=updated_contract, conflicts=conflicts,
        related_snapshots=snapshots,
        review_events=draft.review_events + (event,),
    )


def preview_rejection_guidance(
    draft: ScopedAmendmentDraft, *, principal: dict,
    taraz_rejection: dict,
) -> RejectionGuidance:
    """Suggest ONLY evidenced rejected fields; ambiguous reasons infer nothing.

    An already-verified Taraz receipt is a required input. Free-form reason
    text alone is not evidence of a particular field defect. A new independent
    amendment (linked to both IDs) can be requested separately using
    preview_create_amendment; no replacement, resubmission or auto-fix occurs.
    """
    _require(type(draft) is ScopedAmendmentDraft, "invalid_draft")
    _authorize(principal, draft.org_id, draft.project_id, "canDraft")
    _require(type(taraz_rejection) is dict and
             taraz_rejection.get("orgId") == draft.org_id and
             taraz_rejection.get("projectId") == draft.project_id and
             taraz_rejection.get("originalRequestId") == draft.contract.original_request_id and
             taraz_rejection.get("amendmentId") == draft.contract.amendment_id,
             "scope_denied")
    receipt = _exact(taraz_rejection, (
        "amendmentId", "originalRequestId", "orgId", "projectId",
        "status", "verifiedTarazSource", "reason",
    ), "invalid_rejection")
    _require(receipt["orgId"] == draft.org_id and
             receipt["projectId"] == draft.project_id and
             receipt["originalRequestId"] == draft.contract.original_request_id and
             receipt["amendmentId"] == draft.contract.amendment_id,
             "scope_denied")
    _require(receipt["status"] == "rejected" and
             receipt["verifiedTarazSource"] is True, "unverified_rejection")
    reason = _exact(receipt["reason"], ("text", "affectedFields", "structured"),
                    "invalid_rejection")
    text = reason["text"]
    _require(text is None or (type(text) is str and len(text) <= 500 and
                              not any(ord(ch) < 32 for ch in text)),
             "invalid_rejection")
    _require(type(reason["structured"]) is bool, "invalid_rejection")
    fields = reason["affectedFields"]
    _require(type(fields) is list and len(fields) <= 48 and
             all(type(x) is str and _FIELD.fullmatch(x) for x in fields) and
             len(fields) == len(set(fields)), "invalid_rejection")
    # Structured, explicitly named fields sourced from verified Taraz only.
    valid = bool(text and text.strip()) and reason["structured"] and bool(fields)
    valid = valid and set(fields).issubset(draft.contract.proposed_fields)
    if not valid:
        return RejectionGuidance(
            draft.contract.original_request_id, draft.contract.amendment_id,
            "ambiguous_needs_clarification", text,
            (), ("manual_complete", "request_finance_clarification"),
        )
    hints = tuple(
        RejectionFieldSuggestion(
            field,
            draft.contract.baseline[field],
            draft.contract.proposed_fields[field],
        )
        for field in sorted(fields)
    )
    return RejectionGuidance(
        draft.contract.original_request_id, draft.contract.amendment_id,
        "verified_structured_fields", text, hints,
        ("manual_review_fields", "draft_new_independent_amendment"),
    )
