"""Synthetic local Taraz party catalog -> Radar human review, read-only E4.

Only explicitly imported by isolated integration tests. Never a LAN route.
Requires actual *local* TarazCatalogRead plus host-selected authorized Radar
customer; cannot establish independent *remote* Taraz identity or a legally
verified party. Human choice is journaled only, NEVER linked to the ledger.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json

from radar_party_match_preview import preview_party_matches
from radar_party_review_store import (
    HostPrincipal, PartyReviewStore, ReviewConflict, _json,
)


class LocalCatalogPilotDenied(ValueError):
    """Missing local identity, incomplete candidate set or inconsistent grant."""


class RadarLocalTarazPartyReviewPilot:
    """Complete authorized source snapshot before allowing human review."""

    def __init__(self, *, catalog, reviews: PartyReviewStore,
                 local_source_test_only: bool):
        if local_source_test_only is not True:
            raise LocalCatalogPilotDenied("local test source cannot be deployed")
        try:
            from taraz_mtr_catalog_read import TarazCatalogRead
        except ImportError as exc:
            raise LocalCatalogPilotDenied("detached Taraz source is required") from exc
        if type(catalog) is not TarazCatalogRead or type(reviews) is not PartyReviewStore:
            raise LocalCatalogPilotDenied("local Taraz catalog and Radar review required")
        self.catalog = catalog
        self.reviews = reviews

    def _load_all_candidates(self, *, principal: HostPrincipal,
                             session_token: str, now: datetime):
        scope = self.catalog.scope
        if (type(principal) is not HostPrincipal or
                not principal.authenticated or not principal.active or
                principal.organization_id != scope.org_id or
                scope.project_id not in principal.project_grants or
                "party_match_read" not in principal.capabilities or
                "party_match_decide" not in principal.capabilities or
                principal.role != "taraz_finance_reviewer" or
                "name" not in principal.visible_fields or
                "name" not in scope.party_fields):
            raise PermissionError("current host reviewer organization/field grant required")
        rows = []
        expected_count = None
        offset = 0
        revision = scope.source_revision
        while True:
            # Strict source query is never constructed from a client-chosen
            # company, actor, page limit, field grant, or candidate ID.
            query = json.dumps({
                "kind": "parties", "offset": offset, "limit": 50,
                "expectedRevision": revision,
            }, sort_keys=True, separators=(",", ":"))
            page = self.catalog.read(
                session_token=session_token, query_json=query,
                trusted_now=now,
            )
            if (page.get("orgId") != principal.organization_id or
                    page.get("projectId") != scope.project_id or
                    page.get("revision") != revision or
                    page.get("kind") != "party" or
                    page.get("remoteTarazPeerAuthenticated") is not False or
                    page.get("officialPartyLinkCreated") is not False or
                    page.get("financialPostingPerformed") is not False or
                    page.get("authenticatedLocalCompany") is not True or
                    page.get("offset") != offset or
                    page.get("limit") != 50 or
                    type(page.get("authorizedCount")) is not int or
                    page["authorizedCount"] < 0 or
                    page["authorizedCount"] > 64 or
                    not isinstance(page.get("rows"), list)):
                raise LocalCatalogPilotDenied("untrusted or oversized local candidate source")
            if expected_count is None:
                expected_count = page["authorizedCount"]
            elif expected_count != page["authorizedCount"]:
                raise LocalCatalogPilotDenied("source candidate set changed between pages")
            rows.extend(page["rows"])
            if len(rows) > 64 or len(rows) > expected_count:
                raise LocalCatalogPilotDenied("partial candidate source not acceptable")
            next_offset = page.get("nextOffset")
            if next_offset is None:
                break
            if (type(next_offset) is not int or
                    next_offset <= offset or next_offset != len(rows)):
                raise LocalCatalogPilotDenied("invalid source pagination")
            offset = next_offset
        if len(rows) != expected_count or len(rows) != len({r.get("id") for r in rows}):
            raise LocalCatalogPilotDenied("not all authorized candidates were returned")
        ids = tuple(r["id"] for r in rows)
        if not set(ids) <= principal.allowed_candidate_ids:
            raise PermissionError("Madar reviewer grants do not cover source candidates")
        candidates = [{"organization_id": principal.organization_id,
                       "party_id": r["id"], "read_authorized": True,
                       "name": r["name"]} for r in rows]
        return candidates, ids, revision

    @staticmethod
    def _digest(principal, customer, candidates):
        preview = preview_party_matches(
            customer, candidates,
            scope={"organization_id": principal.organization_id,
                   "server_scoped": True, "party_read_authorized": True,
                   "finance_review_authorized": True,
                   "visible_fields": ("name",)},
        )
        return hashlib.sha256(_json(preview).encode("utf-8")).hexdigest()

    def _source_ref(self):
        return "local-taraz-catalog:" + self.catalog.scope.company_id

    def open_pending(self, *, principal: HostPrincipal, local_session_token: str,
                     project_id: str, review_id: str, temporary_customer: dict,
                     event_id: str, now: datetime):
        if project_id != self.catalog.scope.project_id:
            raise PermissionError("Madar project must match local catalog source")
        candidates, ids, revision = self._load_all_candidates(
            principal=principal, session_token=local_session_token, now=now)
        digest = self._digest(principal, temporary_customer, candidates)
        return self.reviews.open_pending(
            principal=principal, project_id=project_id,
            review_id=review_id, temporary_customer=temporary_customer,
            candidate_records=candidates, visible_fields=("name",),
            authorized_candidate_ids=ids, source_ref=self._source_ref(),
            source_revision=revision, expected_source_digest=digest,
            source_binding_host_confirmed=True, event_id=event_id,
            occurred_at=now,
        )

    def decide(self, *, principal: HostPrincipal, local_session_token: str,
               project_id: str, review_id: str, temporary_customer: dict,
               action: str, candidate_id: str | None,
               expected_version: int, expected_digest: str,
               event_id: str, now: datetime,
               acknowledge_conflicts: bool = False):
        if project_id != self.catalog.scope.project_id:
            raise PermissionError("Madar project must match local catalog source")
        current = self.reviews.read_review(
            principal=principal, project_id=project_id, review_id=review_id)
        candidates, ids, revision = self._load_all_candidates(
            principal=principal, session_token=local_session_token, now=now)
        if (current["sourceRef"] != self._source_ref() or
                current["sourceRevision"] != revision or
                current["snapshotSha256"] != expected_digest or
                current["authorizedCandidateIds"] != list(ids)):
            raise ReviewConflict("stale source, scope or reviewer snapshot")
        digest = self._digest(principal, temporary_customer, candidates)
        if digest != expected_digest:
            raise ReviewConflict("current local catalog or temporary customer changed")
        return self.reviews.record_decision(
            principal=principal, project_id=project_id,
            review_id=review_id, action=action, candidate_id=candidate_id,
            expected_version=expected_version,
            expected_snapshot_sha256=expected_digest,
            current_source_digest=digest,
            current_source_ref=self._source_ref(),
            current_source_revision=revision,
            source_binding_host_confirmed=True,
            acknowledge_conflicts=acknowledge_conflicts,
            event_id=event_id, occurred_at=now, note=None,
        )


__all__ = ["RadarLocalTarazPartyReviewPilot", "LocalCatalogPilotDenied"]
