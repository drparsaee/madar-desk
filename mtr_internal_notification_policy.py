"""Pure E6 *pilot* for Madar/Taraz internal notice and amendment presentation.

Refine 6.26, 6.28, 6.29 / AC-29, AC-31, AC-32. No network, disk, clock,
delivery, status transitions, financial posting, or mutation. All server_*
flags are assertions made by an UPSTREAM AUTHENTICATED SERVER, never proof
when supplied by an arbitrary caller. Production use is blocked until Taraz
receipt provenance, server ACL, atomic dedup and audited delivery are proven.
"""

from __future__ import annotations

from collections.abc import Mapping


ROLES = frozenset({"admin", "editor", "viewer"})
FIELDS = frozenset({"status", "amendment_id", "deficiency_summary", "actor_id", "reference"})
STATUS_VALUES = frozenset({
    "DRAFT", "READY_TO_SUBMIT", "AWAITING_RECEIPT", "UNDER_FINANCE_REVIEW",
    "DEFICIENCY_ASSIGNED", "CORRECTED_READY_FOR_RESUBMIT",
    "FINANCE_APPROVED", "FINANCE_REJECTED", "OFFICIALLY_POSTED",
})
EVENT_KINDS = frozenset({"request_status_changed", "deficiency_assigned",
                         "amendment_status_changed"})
REFERENCE_KINDS = frozenset({"receipt", "document"})


def _id(value, name):
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"{name} must be nonblank, trimmed text")
    return value


def _mapping(value, name):
    if not isinstance(value, Mapping):
        raise PermissionError(f"Unknown {name}; denying request")
    return value


def _id_set(value, name):
    if type(value) not in (list, tuple, frozenset):
        raise PermissionError(f"{name} must be an explicit server-scoped collection")
    items = tuple(_id(v, name) for v in value)
    if len(items) != len(set(items)):
        raise ValueError(f"Duplicate {name}")
    return frozenset(items)


def _scope(scope, *, notification=False):
    scope = _mapping(scope, "scope")
    organization = scope.get("organization_id")
    if (type(organization) is not str or not organization.strip()
            or organization != organization.strip()
            or scope.get("server_scoped") is not True
            or scope.get("actor_authenticated") is not True
            or scope.get("actor_authorized") is not True
            or type(scope.get("actor_role")) is not str
            or scope["actor_role"] not in ROLES):
        raise PermissionError("Authenticated server-scoped role and organization required")
    _id(scope.get("actor_id"), "actor_id")
    projects = _id_set(scope.get("readable_project_ids"), "readable_project_ids")
    if notification and (scope.get("notify_authorized") is not True
                         or scope.get("dedup_snapshot_trusted") is not True):
        raise PermissionError("Notification rights and trusted dedup snapshot required")
    fields = _id_set(scope.get("visible_fields"), "visible_fields")
    if fields - FIELDS:
        raise PermissionError("Unknown/unauthorized presentation field")
    return organization, projects, fields


def _within_scope(record, organization, projects, *, request_id=None):
    record = _mapping(record, "record")
    if (record.get("organization_id") != organization
            or type(record.get("project_id")) is not str
            or record["project_id"] not in projects
            or record.get("server_read_authorized") is not True):
        raise PermissionError("Record crosses organization/project/ACL boundary")
    if request_id is not None and record.get("original_request_id") != request_id:
        raise PermissionError("Amendment belongs to a different original request")
    return record


def _allowed_fields(record):
    return _id_set(record.get("visible_fields"), "record visible_fields")


def _status(value):
    if type(value) is not str or value not in STATUS_VALUES:
        raise ValueError("Unknown status; cannot interpret as finance approval")
    return value


def _reference(reference, *, organization, project_id, amendment_id, fields):
    """Return a linkable **display reference** only with full server attestation.

    Reject malformed/unknown provenance entirely. A known unverified receipt
    is withheld, never shown as an official reference. No signature or source
    is independently validated by this pure function.
    """
    if reference is None:
        return None
    reference = _mapping(reference, "receipt provenance")
    required = (
        "reference_id", "reference_kind", "organization_id", "project_id",
        "amendment_id", "source_system", "source_actor_id", "received_at",
        "server_supplied", "source_actor_verified", "source_provenance_verified",
        "correlation_verified",
    )
    if any(key not in reference for key in required):
        raise PermissionError("Unknown receipt trust contract")
    if (reference.get("organization_id") != organization
            or reference.get("project_id") != project_id
            or reference.get("amendment_id") != amendment_id):
        raise PermissionError("Receipt reference scope mismatch")
    if (type(reference["source_system"]) is not str
            or reference["source_system"] != "taraz"
            or type(reference["reference_kind"]) is not str
            or reference["reference_kind"] not in REFERENCE_KINDS
            or reference["server_supplied"] is not True):
        raise PermissionError("Untrusted receipt origin")
    if any(type(reference[key]) is not bool for key in (
        "source_actor_verified", "source_provenance_verified", "correlation_verified",
    )):
        raise PermissionError("Unknown receipt trust state")
    if not all(reference[key] for key in (
        "source_actor_verified", "source_provenance_verified", "correlation_verified",
    )):
        return None
    _id(reference.get("reference_id"), "reference_id")
    _id(reference.get("source_actor_id"), "source_actor_id")
    _id(reference.get("received_at"), "received_at")
    if "reference" not in fields:
        return None
    return {
        "reference_id": reference["reference_id"],
        "reference_kind": reference["reference_kind"],
        "source_system": "taraz",
        "source_actor_id": reference["source_actor_id"]
        if "actor_id" in fields else None,
        "received_at": reference["received_at"],
        "provenance": "upstream_server_verified_claim_not_independently_verified",
    }


def summarize_amendments(original, amendments, *, scope):
    """Read-only AC-29/32 view; never computes or changes the original status."""
    organization, projects, fields = _scope(scope)
    original = _within_scope(original, organization, projects)
    request_id = _id(original.get("request_id"), "original request_id")
    original_status = _status(original.get("official_status"))
    if (original.get("official_status_server_trusted") is not True
            or original.get("official_status_source") != "taraz"):
        raise PermissionError("Original official status requires trusted Taraz provenance")
    if type(amendments) not in (list, tuple):
        raise PermissionError("Server-authorized amendment sequence required")
    seen = set()
    rows = []
    # Validate ALL records before returning anything; a foreign item fails
    # the full batch rather than causing a partially populated cross-tenant UI.
    for record in amendments:
        amendment = _within_scope(
            record, organization, projects, request_id=request_id,
        )
        if amendment["project_id"] != original["project_id"]:
            raise PermissionError("Amendment project differs from original")
        identifier = _id(amendment.get("amendment_id"), "amendment_id")
        if identifier in seen or identifier == request_id:
            raise ValueError("Ambiguous amendment identifier")
        seen.add(identifier)
        status = _status(amendment.get("status"))
        if (type(amendment.get("status_source")) is not str
                or amendment["status_source"] not in ("madar", "taraz")
                or amendment.get("status_source_trusted") is not True):
            raise PermissionError("Amendment status provenance untrusted")
        if (status in {"FINANCE_APPROVED", "FINANCE_REJECTED", "OFFICIALLY_POSTED"}
                and amendment["status_source"] != "taraz"):
            raise PermissionError("Financial decision/official posting must originate at Taraz")
        _id(amendment.get("status_updated_at"), "status_updated_at")
        row_fields = _allowed_fields(amendment)
        allowed = row_fields.intersection(fields)
        link = (_reference(
            amendment.get("receipt_reference"),
            organization=organization, project_id=original["project_id"],
            amendment_id=identifier, fields=allowed,
        ) if "reference" in allowed else None)
        if status == "OFFICIALLY_POSTED":
            # A read-only status assertion without trusted provenance is NOT
            # enough to claim that an official document was registered.
            # This check uses trusted-scope metadata, not the viewer's
            # permission to display the reference ID.
            provenance = _reference(
                amendment.get("receipt_reference"),
                organization=organization, project_id=original["project_id"],
                amendment_id=identifier, fields=FIELDS,
            )
            if provenance is None or provenance["reference_kind"] != "document":
                raise PermissionError("Official posting requires trusted Taraz document reference")
        rows.append({
            "amendment_id": identifier if "amendment_id" in allowed else None,
            "status": status if "status" in allowed else None,
            "status_source": amendment["status_source"] if "status" in allowed else None,
            "status_updated_at": amendment["status_updated_at"]
            if "status" in allowed else None,
            "receipt_reference": link,
        })
    return {
        "kind": "read_only_amendment_summary_pilot",
        "original_request_id": request_id,
        "original_official_status": original_status if "status" in fields else None,
        "amendments": rows,
        "amendment_count": len(rows),
        "original_status_unchanged": True,
        "official_document_modified": False,
    }


def plan_internal_notifications(event, recipients, *, scope, seen_event_keys):
    """Plan *internal-only* AC-31 notices, never deliver or persist anything.

    The server must already have authenticated the scope/recipients and must
    atomically persist event-key dedup (with correct payload binding).
    Neither status change nor missing receipt can authorize a Taraz resend.
    """
    organization, projects, scope_fields = _scope(scope, notification=True)
    event = _within_scope(event, organization, projects)
    if event.get("server_event_trusted") is not True:
        raise PermissionError("Status/deficiency event source untrusted")
    event_key = _id(event.get("event_key"), "event_key")
    request_id = _id(event.get("original_request_id"), "original_request_id")
    kind = event.get("event_kind")
    if type(kind) is not str or kind not in EVENT_KINDS:
        raise ValueError("Unknown notification event kind")
    _id(event.get("actor_id"), "event actor_id")
    _id(event.get("occurred_at"), "occurred_at")
    rev_before = event.get("previous_revision")
    rev_after = event.get("revision")
    authoritative = scope.get("authoritative_revision")
    if (type(rev_before) is not int or type(rev_after) is not int
            or type(authoritative) is not int or rev_before < 0
            or rev_after <= rev_before or authoritative != rev_after):
        raise PermissionError("Stale or untrusted event revision")
    before = _status(event.get("previous_status"))
    after = _status(event.get("status"))
    if kind == "request_status_changed" and before == after:
        meaningful = False
    elif kind == "amendment_status_changed":
        _id(event.get("amendment_id"), "amendment_id")
        meaningful = before != after
    elif kind == "deficiency_assigned":
        _id(event.get("assigned_user_id"), "assigned_user_id")
        meaningful = after == "DEFICIENCY_ASSIGNED" and before != after
    else:
        meaningful = before != after
    seen = _id_set(seen_event_keys, "seen_event_keys")
    if type(recipients) not in (list, tuple):
        raise PermissionError("Server-authorized recipient list required")
    users = set()
    result = []
    for recipient in recipients:
        recipient = _mapping(recipient, "recipient")
        if (recipient.get("organization_id") != organization
                or recipient.get("server_read_authorized") is not True
                or type(recipient.get("role")) is not str
                or recipient["role"] not in ROLES):
            raise PermissionError("Recipient organization/role/ACL not trusted")
        user_id = _id(recipient.get("user_id"), "recipient user_id")
        if user_id in users:
            raise ValueError("Duplicate recipient")
        users.add(user_id)
        user_projects = _id_set(recipient.get("readable_project_ids"),
                                "recipient readable_project_ids")
        related_requests = _id_set(recipient.get("related_request_ids"),
                                   "recipient related_request_ids")
        recipient_fields = _allowed_fields(recipient)
        if (not meaningful or event_key in seen or
                event["project_id"] not in user_projects or
                request_id not in related_requests or
                recipient.get("internal_notifications_enabled") is not True):
            continue
        fields = scope_fields.intersection(recipient_fields)
        payload = {
            "channel": "internal_only",
            "event_key": event_key,
            "recipient_id": user_id,
            "original_request_id": request_id,
            "event_kind": kind,
            "status": after if "status" in fields else None,
            "amendment_id": event.get("amendment_id")
            if kind == "amendment_status_changed" and "amendment_id" in fields else None,
            "deficiency_summary": event.get("deficiency_summary")
            if kind == "deficiency_assigned" and "deficiency_summary" in fields else None,
            "actor_id": event["actor_id"] if "actor_id" in fields else None,
        }
        if payload["deficiency_summary"] is not None and type(payload["deficiency_summary"]) is not str:
            raise ValueError("Deficiency summary must be text")
        result.append(payload)
    return {
        "kind": "internal_notification_plan_pilot",
        "event_key": event_key,
        "duplicate_event": event_key in seen,
        "meaningful_change": meaningful,
        "notifications": result,
        "external_deliveries": [],
        "send_or_resend_performed": False,
        "any_mutation_performed": False,
    }
