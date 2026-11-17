"""E4 synthetic-only wrong-party-link impact preview and selective intent.

Pure decisions, NO state writes, official Taraz API, network, or LAN mount.
Inputs must originate from an independently authenticated host, but this
module cannot authenticate their provenance and MUST NOT be used as authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re

from radar_party_review_store import HostPrincipal


_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_ALLOWED_STATES = frozenset({"draft", "open", "sent", "posted", "closed"})
_EDITABLE_STATES = frozenset({"draft", "open"})
_MAX_ROWS = 128
_PREVIEW_KEYS = frozenset({
    "organizationId", "projectId", "customerId", "revision", "oldPartyId",
    "proposedPartyId", "rows", "snapshotSha256",
    "allHostSuppliedDependenciesVisible", "remoteTarazAuthorityVerified",
    "officialDocumentsChanged", "financeRequestsChanged", "partyLinkChanged",
})
_ROW_KEYS = frozenset({"orderId", "state", "beforePartyId", "proposedPartyId",
                       "financeRequestId", "documentIds",
                       "eligibleForSeparateManualCorrection"})


class ImpactDenied(ValueError):
    """Denied stale, incomplete, unauthorized or inconsistent impact source."""


def _id(value: object) -> str:
    if type(value) is not str or not _ID.fullmatch(value):
        raise ImpactDenied("invalid identifier")
    return value


@dataclass(frozen=True, slots=True)
class LinkedOrder:
    order_id: str
    organization_id: str
    project_id: str
    customer_id: str
    party_id: str
    state: str
    finance_request_id: str | None = None
    document_ids: tuple[str, ...] = ()

    def __post_init__(self):
        for value in (self.order_id, self.organization_id, self.project_id,
                      self.customer_id, self.party_id):
            _id(value)
        if type(self.state) is not str or self.state not in _ALLOWED_STATES:
            raise ImpactDenied("invalid order state")
        if self.finance_request_id is not None:
            _id(self.finance_request_id)
        if type(self.document_ids) is not tuple or len(self.document_ids) > 16:
            raise ImpactDenied("invalid linked document set")
        for value in self.document_ids:
            _id(value)
        if len(set(self.document_ids)) != len(self.document_ids):
            raise ImpactDenied("duplicate linked document")


@dataclass(frozen=True, slots=True)
class HostImpactSnapshot:
    """Host supplied synthetic fixture; NOT proof of a complete actual ledger."""
    organization_id: str
    project_id: str
    customer_id: str
    old_party_id: str
    proposed_party_id: str
    revision: int
    observed_at: datetime
    expected_linked_order_count: int
    linked_orders: tuple[LinkedOrder, ...]

    def __post_init__(self):
        for value in (self.organization_id, self.project_id, self.customer_id,
                      self.old_party_id, self.proposed_party_id):
            _id(value)
        if self.old_party_id == self.proposed_party_id:
            raise ImpactDenied("new party must differ")
        if type(self.revision) is not int or self.revision < 0:
            raise ImpactDenied("invalid host revision")
        if (type(self.observed_at) is not datetime or self.observed_at.tzinfo is None
                or self.observed_at.utcoffset() is None):
            raise ImpactDenied("trusted UTC snapshot time required")
        if (type(self.expected_linked_order_count) is not int or
                not 0 <= self.expected_linked_order_count <= _MAX_ROWS or
                type(self.linked_orders) is not tuple or
                len(self.linked_orders) != self.expected_linked_order_count):
            raise ImpactDenied("incomplete or oversized dependency snapshot")
        seen = set()
        for row in self.linked_orders:
            if type(row) is not LinkedOrder:
                raise ImpactDenied("typed order snapshot required")
            if (row.organization_id != self.organization_id or
                    row.project_id != self.project_id or
                    row.customer_id != self.customer_id or
                    row.party_id != self.old_party_id or row.order_id in seen):
                raise ImpactDenied("inconsistent dependency snapshot")
            seen.add(row.order_id)


def _authorize(principal: HostPrincipal, snapshot: HostImpactSnapshot,
               allowed_order_ids: frozenset[str], allowed_document_ids: frozenset[str]):
    if (type(principal) is not HostPrincipal or type(snapshot) is not HostImpactSnapshot
            or type(allowed_order_ids) is not frozenset
            or type(allowed_document_ids) is not frozenset):
        raise ImpactDenied("host-derived typed inputs required")
    if (principal.authenticated is not True or principal.active is not True or
            principal.role != "taraz_finance_reviewer" or
            "party_link_impact_read" not in principal.capabilities or
            snapshot.organization_id != principal.organization_id or
            snapshot.project_id not in principal.project_grants):
        raise PermissionError("current financial reviewer and project grant required")
    order_ids = frozenset(row.order_id for row in snapshot.linked_orders)
    doc_ids = frozenset(doc for row in snapshot.linked_orders
                        for doc in row.document_ids)
    if (not all(type(value) is str and _ID.fullmatch(value)
                for value in allowed_order_ids | allowed_document_ids) or
            not order_ids <= allowed_order_ids or not doc_ids <= allowed_document_ids):
        raise PermissionError("complete host row/document visibility required")


def impact_preview(*, principal: HostPrincipal, snapshot: HostImpactSnapshot,
                   allowed_order_ids: frozenset[str],
                   allowed_document_ids: frozenset[str],
                   synthetic_only: bool, now: datetime) -> dict:
    """Preview all synthetic dependencies; never authorize an actual link edit."""
    if synthetic_only is not True:
        raise ImpactDenied("pilot cannot be mounted in production")
    _authorize(principal, snapshot, allowed_order_ids, allowed_document_ids)
    if type(now) is not datetime or now.tzinfo is None or now.utcoffset() is None:
        raise ImpactDenied("trusted time required")
    age = (now.astimezone(timezone.utc) -
           snapshot.observed_at.astimezone(timezone.utc)).total_seconds()
    if not -30 <= age <= 300:
        raise ImpactDenied("stale dependency snapshot")

    rows = []
    for row in sorted(snapshot.linked_orders, key=lambda item: item.order_id):
        editable = (row.state in _EDITABLE_STATES and
                    row.finance_request_id is None and not row.document_ids)
        rows.append({"orderId": row.order_id, "state": row.state,
                     "beforePartyId": row.party_id,
                     "proposedPartyId": snapshot.proposed_party_id,
                     "financeRequestId": row.finance_request_id,
                     "documentIds": list(row.document_ids),
                     "eligibleForSeparateManualCorrection": editable})
    evidence = {"organizationId": snapshot.organization_id,
                "projectId": snapshot.project_id,
                "customerId": snapshot.customer_id,
                "revision": snapshot.revision,
                "oldPartyId": snapshot.old_party_id,
                "proposedPartyId": snapshot.proposed_party_id,
                "rows": rows}
    digest = hashlib.sha256(json.dumps(evidence, sort_keys=True,
                    separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    return {**evidence, "snapshotSha256": digest,
            "allHostSuppliedDependenciesVisible": True,
            "remoteTarazAuthorityVerified": False,
            "officialDocumentsChanged": False,
            "financeRequestsChanged": False,
            "partyLinkChanged": False}


def selective_correction_intent(*, preview: dict, principal: HostPrincipal,
                                selected_order_ids: tuple[str, ...],
                                expected_revision: int, expected_digest: str,
                                explicit_manual_action: bool) -> dict:
    """Create non-persisted intent only; never modify an order or ledger."""
    if (type(preview) is not dict or set(preview) != _PREVIEW_KEYS
            or preview.get("allHostSuppliedDependenciesVisible") is not True
            or preview.get("remoteTarazAuthorityVerified") is not False
            or preview.get("officialDocumentsChanged") is not False
            or preview.get("financeRequestsChanged") is not False
            or preview.get("partyLinkChanged") is not False):
        raise ImpactDenied("untrusted impact preview")
    if (type(principal) is not HostPrincipal or not principal.authenticated or
            not principal.active or principal.role != "taraz_finance_reviewer" or
            "party_link_correction_review" not in principal.capabilities or
            preview.get("organizationId") != principal.organization_id or
            preview.get("projectId") not in principal.project_grants):
        raise PermissionError("authorized finance reviewer required")
    if explicit_manual_action is not True:
        raise PermissionError("explicit human selection required")
    if (type(expected_revision) is not int or expected_revision != preview.get("revision")
            or type(expected_digest) is not str or not _DIGEST.fullmatch(expected_digest)
            or preview.get("snapshotSha256") != expected_digest):
        raise ImpactDenied("stale impact preview")
    for key in ("organizationId", "projectId", "customerId", "oldPartyId", "proposedPartyId"):
        _id(preview.get(key))
    if preview["oldPartyId"] == preview["proposedPartyId"]:
        raise ImpactDenied("invalid proposed party")
    if (type(selected_order_ids) is not tuple or
            not 0 < len(selected_order_ids) <= _MAX_ROWS or
            len(set(selected_order_ids)) != len(selected_order_ids)):
        raise ImpactDenied("explicit distinct order selections required")
    rows = preview.get("rows")
    if type(rows) is not list or len(rows) > _MAX_ROWS:
        raise ImpactDenied("invalid dependency rows")
    available = {}
    for row in rows:
        if type(row) is not dict or set(row) != _ROW_KEYS:
            raise ImpactDenied("invalid dependency row schema")
        order_id = _id(row["orderId"])
        doc_ids = row["documentIds"]
        if (order_id in available or row["state"] not in _ALLOWED_STATES or
                row["beforePartyId"] != preview["oldPartyId"] or
                row["proposedPartyId"] != preview["proposedPartyId"] or
                (row["financeRequestId"] is not None and
                 (type(row["financeRequestId"]) is not str or
                  not _ID.fullmatch(row["financeRequestId"]))) or
                type(doc_ids) is not list or len(doc_ids) > 16 or
                any(type(v) is not str or not _ID.fullmatch(v) for v in doc_ids) or
                len(set(doc_ids)) != len(doc_ids)):
            raise ImpactDenied("invalid or repeated dependency row")
        editable = (row["state"] in _EDITABLE_STATES and
                    row["financeRequestId"] is None and not doc_ids)
        if row["eligibleForSeparateManualCorrection"] is not editable:
            raise ImpactDenied("inconsistent eligibility")
        available[order_id] = row
    if [r["orderId"] for r in rows] != sorted(available):
        raise ImpactDenied("invalid dependency ordering")
    evidence = {key: preview[key] for key in (
        "organizationId", "projectId", "customerId", "revision",
        "oldPartyId", "proposedPartyId", "rows")}
    computed = hashlib.sha256(json.dumps(evidence, sort_keys=True,
                     separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    if computed != expected_digest:
        raise ImpactDenied("modified impact preview")
    for order_id in selected_order_ids:
        _id(order_id)
        row = available.get(order_id)
        if (row is None or row.get("eligibleForSeparateManualCorrection") is not True
                or row.get("financeRequestId") is not None or row.get("documentIds") != []
                or row.get("state") not in _EDITABLE_STATES):
            raise ImpactDenied("selected dependency requires separate finance review")
    return {"status": "UNSENT_SELECTION_INTENT", "selectedOrderIds": list(selected_order_ids),
            "expectedHostRevision": expected_revision, "sourceDigest": expected_digest,
            "originalPartyId": preview["oldPartyId"],
            "proposedPartyId": preview["proposedPartyId"],
            "officialDocumentsChanged": False, "financeRequestsChanged": False,
            "ordersChanged": False, "partyLinkChanged": False,
            "approvedToApplyOrSend": False}


__all__ = ["ImpactDenied", "LinkedOrder", "HostImpactSnapshot",
           "impact_preview", "selective_correction_intent"]
