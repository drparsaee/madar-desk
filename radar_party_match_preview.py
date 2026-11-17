"""E4 pilot: explain *supplied* same-organization party candidates, without I/O.

This is not a Taraz reader or an authority for organization/field permissions.
The upstream server must authenticate the reviewer, enforce row/field ACLs,
and supply only candidates already authorized for that reviewer. Explicit
scope and per-row assertions are checked again here, fail-closed. Client-
provided assertions alone are NOT sufficient for production authorization.

Refine 6.11-6.14: keep every supplied authorized candidate (including an
official-ID disagreement), explain four permitted fields, and leave linking,
rejecting, and official-party creation to an authorized human financial actor.
There is no threshold, score, rank, inferred official ID, persistence, or API.
"""

from __future__ import annotations

import re
import unicodedata


FIELDS = ("official_id", "name", "phone", "address")
_PERSIAN_CHARACTERS = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک"})
_DIGITS = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"
)


def _text(value):
    if value is None:
        return None
    if type(value) is not str:
        raise ValueError("Party comparison fields must be text or null")
    return value if value.strip() else None


def _normalize(value, field):
    """Conservative, HEURISTIC formatting normalization, not identity proof."""
    if value is None:
        return None
    result = unicodedata.normalize("NFC", value).translate(_DIGITS)
    if field == "official_id":
        # No numeric parsing, length validation, country inference, or zero loss.
        return result.strip()
    if field == "phone":
        # Preserve +98 vs 0 and all leading zeroes; only strip visual separators.
        return re.sub(r"[\s\-()]", "", result)
    result = result.translate(_PERSIAN_CHARACTERS).replace("ـ", "")
    result = result.replace("\u200c", " ").replace("\u200d", " ")
    return " ".join(result.split()).casefold()


def _compare(left, right, field, verified_left, verified_right):
    source_value = _text(left)
    candidate_value = _text(right)
    if source_value is None and candidate_value is None:
        state = "missing_both"
    elif source_value is None:
        state = "missing_temporary"
    elif candidate_value is None:
        state = "missing_candidate"
    else:
        state = ("equal_after_heuristic_normalization"
                 if _normalize(source_value, field) == _normalize(candidate_value, field)
                 else "different")
    result = {
        "temporary_value": source_value,
        "candidate_value": candidate_value,
        "comparison": state,
    }
    if field == "official_id":
        # This is a claim in the INPUT, not verification by this engine.
        result["upstream_claimed_verified"] = {
            "temporary": verified_left, "candidate": verified_right,
        }
    if field in ("name", "address") and source_value and candidate_value:
        # Tokens are only explanations. They are NOT a relevance threshold.
        tokens = set(_normalize(source_value, field).split())
        common = tokens.intersection(_normalize(candidate_value, field).split())
        result["heuristic_shared_words"] = sorted(common)
    return result


def _scope_or_deny(scope, customer, candidates):
    if type(scope) is not dict or type(customer) is not dict:
        raise PermissionError("Authorized organization scope is required")
    org = scope.get("organization_id")
    if (type(org) is not str or not org or org != org.strip()
            or scope.get("server_scoped") is not True
            or scope.get("party_read_authorized") is not True
            or scope.get("finance_review_authorized") is not True):
        raise PermissionError("Authorized organization scope is required")
    visible = scope.get("visible_fields")
    if (type(visible) not in (list, tuple, frozenset)
            or any(type(field) is not str or field not in FIELDS for field in visible)
            or len(visible) != len(set(visible))):
        raise PermissionError("Explicit field permissions are required")
    if (customer.get("organization_id") != org
            or type(customer.get("customer_id")) is not str
            or not customer["customer_id"].strip()):
        raise PermissionError("Authorized organization scope is required")
    if type(candidates) not in (list, tuple):
        raise PermissionError("Server-scoped candidate list is required")
    seen = set()
    for party in candidates:
        if (type(party) is not dict
                or party.get("organization_id") != org
                or party.get("read_authorized") is not True
                or type(party.get("party_id")) is not str
                or not party["party_id"].strip()):
            # Reject the *whole* batch; never return partial cross-org results.
            raise PermissionError("Candidate scope/authorization is not valid")
        party_id = party["party_id"]
        if party_id in seen:
            raise ValueError("Duplicate candidate party ID")
        seen.add(party_id)
    return org, frozenset(visible)


def _claimed_verified(record, field_allowed):
    if not field_allowed:
        return False
    marker = record.get("official_id_source_verified", False)
    if type(marker) is not bool:
        raise ValueError("Official ID source claim must be boolean")
    if marker and _text(record.get("official_id")) is None:
        raise ValueError("Claimed verified official ID cannot be missing")
    return marker


def preview_party_matches(temporary_customer, candidates, *, scope):
    """Return *every* authorized supplied candidate, preserving input order.

    Required scope keys:
      organization_id, server_scoped=True, party_read_authorized=True,
      finance_review_authorized=True, visible_fields=[subset of four FIELDS].
    Required row keys: organization_id, party_id, read_authorized=True.
    Temporary customer: organization_id, customer_id. Optional comparison keys
    in both: official_id, name, phone, address, official_id_source_verified.

    True in official_id_source_verified only says an upstream source CLAIMED
    verification. This module cannot verify the provenance or ID's validity.
    A disagreement between two such claims is shown as a conflict, never
    discarded because another field resembles it.
    """
    org, visible_fields = _scope_or_deny(scope, temporary_customer, candidates)
    compare_id = "official_id" in visible_fields
    temp_claim = _claimed_verified(temporary_customer, compare_id)
    result = []
    for party in candidates:
        party_claim = _claimed_verified(party, compare_id)
        fields = {}
        for field in FIELDS:
            if field not in visible_fields:
                # Do not inspect or echo values without field-level permission.
                fields[field] = {"comparison": "not_authorized"}
            else:
                fields[field] = _compare(
                    temporary_customer.get(field), party.get(field), field,
                    temp_claim, party_claim,
                )
        conflicts = []
        if (compare_id and temp_claim and party_claim
                and fields["official_id"]["comparison"] == "different"):
            conflicts.append("conflicting_upstream_claimed_verified_official_ids")
        result.append({
            "party_id": party["party_id"],
            "fields": fields,
            "conflicts": conflicts,
            "requires_human_financial_decision": True,
        })
    return {
        "kind": "synthetic_party_match_preview",
        "organization_id": org,
        "temporary_customer_id": temporary_customer["customer_id"],
        "candidates": result,
        "candidate_count": len(result),
        "manual_financial_review_required": True,
        "official_id_verified_by_engine": False,
        "automatic_link_or_creation_performed": False,
        "comparison_normalization": "heuristic_not_official_verification",
    }
