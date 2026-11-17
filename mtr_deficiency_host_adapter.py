"""Host-only E3 deficiency adapter. No LAN route, peer traffic or finance posting.

The host owns service.lock, bridge._lock, account_for and the saved card/project.
All case transitions delegate to the existing durable DeficiencyStore. A
receipt requires an independently trusted Python-side verifier, injected at
construction by the host operator. The default is None: referral is denied.

This module neither authenticates a Taraz receipt nor reads an official
finance database. A browser-provided verified_by_adapter flag has NO API.
"""
from __future__ import annotations

from contextlib import ExitStack
from datetime import datetime
import hashlib
import json
import re

from mtr_deficiency_store import DeficiencyStore
from mtr_deficiency_workflow import (
    Baseline, FinanceReceipt, Principal, ReviewCase,
)


class HostDeficiencyError(ValueError):
    """Invalid host command or unavailable host-owned snapshot."""


_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z", re.ASCII)
_SHA = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_MAX_STATE_PAIR = 65536
_MAX_MARKER_BYTES = 4096
_REVIEW = "finance_deficiency_refer"
_RESOLVE = "deficiency_resolve"
_SEND = "finance_request_resubmit"
_MARKER_FIELDS = frozenset({
    "requestId", "revision", "reviewState", "expectedReceiptId",
    "receiptGeneration", "previousReceiptIds", "previousSendKeys",
})


def _id(value, name="identifier"):
    if type(value) is not str or not _ID.fullmatch(value):
        raise HostDeficiencyError("invalid " + name)
    return value


def _sha(value):
    if type(value) is not str or not _SHA.fullmatch(value):
        raise HostDeficiencyError("expected SHA-256 required")
    return value


def _rev(value):
    if type(value) is not int or not 1 <= value < 2**31:
        raise HostDeficiencyError("positive saved revision required")
    return value


def _canonical(value, limit):
    try:
        raw = json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise HostDeficiencyError("invalid host-saved JSON") from exc
    if len(raw) > limit:
        raise HostDeficiencyError("host-saved metadata exceeds bound")
    return raw


def _time(value):
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise HostDeficiencyError("host timestamp must include timezone")
    return value


def _names(value, name):
    if (type(value) is not list or len(value) > 64
            or any(type(item) is not str or not _ID.fullmatch(item) for item in value)
            or len(value) != len(set(value))):
        raise HostDeficiencyError("invalid saved " + name)
    return frozenset(value)


def _saved_case(state, org_id, project_id, task_id):
    """Snapshot current project/card, never a client-provided revision/digest.

    The explicit mtrDeficiencyRequest card marker is a PROVISIONAL host-pilot
    binding, not proof of official Taraz review. It must originate from
    trusted previous host persistence; a matching verified receipt is
    independently required before the first referral.
    """
    if (type(state) is not dict or type(state.get("projects")) is not list
            or type(state.get("tasks")) is not list or
            state.get("__offline") is True or
            state.get("__remoteRevision") == "offline"):
        raise PermissionError("host-saved live state required")
    projects = [p for p in state["projects"]
                if type(p) is dict and p.get("id") == project_id]
    tasks = [t for t in state["tasks"]
             if type(t) is dict and t.get("id") == task_id
             and t.get("projectId") == project_id]
    if len(projects) != 1 or len(tasks) != 1:
        raise PermissionError("scoped saved project/task unavailable")
    project, task = projects[0], tasks[0]
    marker = task.get("mtrDeficiencyRequest")
    if type(marker) is not dict or set(marker) != _MARKER_FIELDS:
        raise PermissionError("trusted saved deficiency binding missing")
    if len(_canonical(marker, _MAX_MARKER_BYTES)) > _MAX_MARKER_BYTES:
        raise HostDeficiencyError("invalid saved marker")
    request_id = _id(marker["requestId"], "requestId")
    revision = _rev(marker["revision"])
    _id(marker["expectedReceiptId"], "expectedReceiptId")
    generation = _rev(marker["receiptGeneration"])
    if type(marker["reviewState"]) is not str or marker["reviewState"] not in (
        "IN_FINANCE_REVIEW", "AWAITING_FINANCE_REVIEW",
    ):
        raise HostDeficiencyError("invalid saved review state")
    prior_receipts = _names(marker["previousReceiptIds"], "receipt history")
    prior_keys = _names(marker["previousSendKeys"], "send-key history")
    if marker["expectedReceiptId"] in prior_receipts:
        raise HostDeficiencyError("receipt already consumed in saved history")
    if ("mtrDeficiencyFields" in task and
            (type(task["mtrDeficiencyFields"]) is not dict or
             len(task["mtrDeficiencyFields"]) > 48)):
        raise HostDeficiencyError("invalid saved correction fields")
    digest = hashlib.sha256(
        _canonical({"project": project, "task": task}, _MAX_STATE_PAIR)
    ).hexdigest()
    return (
        Baseline(request_id, org_id, project_id, revision, digest),
        marker, task,
    )


def _project_grants(account, project_id):
    if type(account) is not dict or account.get("disabled") is True:
        raise PermissionError("inactive host account")
    name = _id(account.get("username"), "host account")
    role = account.get("role")
    if role not in ("admin", "editor"):
        raise PermissionError("host task editor/admin role required")
    grants = account.get("projects")
    if role == "admin":
        if grants is not None:
            raise PermissionError("unexpected administrator project restriction")
    elif (type(grants) is not list or not 1 <= len(grants) <= 500
          or any(type(x) is not str or not _ID.fullmatch(x) for x in grants)
          or len(grants) != len(set(grants))
          or project_id not in grants):
        raise PermissionError("explicit project membership required")
    return name, role


class DeficiencyHostAdapter:
    """Independent host-only adapter. No method is registered as a LAN route.

    reviewer_usernames is host-operator owned, since LanService has only
    admin/editor/viewer roles. It must not come from client JSON. A receipt
    verifier may be injected only as trusted Python configuration; absent
    real Taraz authentication the default None makes all referrals DENY.
    """

    def __init__(
        self, service, store: DeficiencyStore, *,
        org_id: str, reviewer_usernames: frozenset[str] = frozenset(),
        verified_receipt_source=None,
    ):
        _id(org_id, "host organization")
        if not isinstance(store, DeficiencyStore):
            raise HostDeficiencyError("durable DeficiencyStore required")
        if (type(reviewer_usernames) is not frozenset or
                any(type(item) is not str or not _ID.fullmatch(item)
                    for item in reviewer_usernames)):
            raise HostDeficiencyError("trusted reviewer allowlist required")
        if (not hasattr(service, "lock") or not hasattr(service, "bridge") or
                not hasattr(service.bridge, "_lock") or
                not callable(getattr(service, "account_for", None)) or
                not callable(getattr(service.bridge, "getState", None)) or
                type(getattr(service, "users", None)) is not dict):
            raise HostDeficiencyError("LanService account/bridge contract required")
        if (verified_receipt_source is not None and
                not callable(getattr(verified_receipt_source,
                                     "verified_receipt_for", None))):
            raise HostDeficiencyError("trusted receipt verifier interface required")
        self.service = service
        self.store = store
        self.org_id = org_id
        self.reviewer_usernames = reviewer_usernames
        self._verified_receipt_source = verified_receipt_source

    def _scope(self, *, token, project_id, task_id):
        if (type(token) is not str or not 32 <= len(token) <= 256 or
                not token.isascii()):
            raise PermissionError("active LAN session token required")
        project_id = _id(project_id, "projectId")
        task_id = _id(task_id, "taskId")
        connection = getattr(self.service.bridge, "connection", None)
        if type(connection) is dict and connection.get("mode") == "client":
            raise PermissionError("client-side bridge cannot act as host")
        account = self.service.account_for(token)
        name, role = _project_grants(account, project_id)
        if self.service.users.get(name) is not account:
            # A detached or replaced account snapshot is not authoritative.
            raise PermissionError("host account registry mismatch")
        reviewer = (
            name in self.reviewer_usernames and
            (role == "admin" or account.get("financeEdit") is True)
        )
        capabilities = {_RESOLVE}
        if reviewer:
            capabilities.update((_REVIEW, _SEND))
        principal = Principal(
            user_id=name, org_id=self.org_id,
            role="taraz_finance_reviewer" if reviewer else "madar_user",
            projects=frozenset({project_id}),
            capabilities=frozenset(capabilities),
            authenticated=True, active=True,
        )
        state = self.service.bridge.getState()
        current, marker, task = _saved_case(
            state, self.org_id, project_id, task_id,
        )
        return principal, current, marker, task

    def _case(self, current, *, case_revision, case_digest):
        _rev(case_revision)
        _sha(case_digest)
        return Baseline(
            current.request_id, current.org_id,
            current.project_id, case_revision, case_digest,
        )

    @staticmethod
    def _assert_current(current, expected_revision, expected_digest):
        _rev(expected_revision)
        _sha(expected_digest)
        if current.revision != expected_revision or current.digest != expected_digest:
            raise PermissionError("stale host-saved task/project revision")

    @staticmethod
    def _safe_result(result):
        if (result.get("financialEventCreated") is not False or
                result.get("postingPerformed") is not False or
                result.get("officialDocumentId") is not None):
            raise RuntimeError("unexpected official finance operation")
        return {
            **result,
            "hostAuthenticated": True,
            "tarazReceiptIndependentlyVerifiedInResponse": False,
            "transportState": "NOT_SENT_BY_HOST_ADAPTER",
        }

    def _read_scoped(self, base, principal):
        result = self.store.read_case(baseline=base, principal=principal)
        # A reviewer's old username in the stored history must not preserve
        # access after the finance-review allowlist/financeEdit is revoked.
        is_original_reviewer = bool(
            result["events"] and result["events"][0]["actorId"] == principal.user_id
        )
        if (is_original_reviewer and principal.user_id != result["assigneeId"]
                and principal.role != "taraz_finance_reviewer"):
            raise PermissionError("finance review access has been revoked")
        return result

    def read_case(self, *, token, project_id, task_id,
                  case_revision, case_digest,
                  expected_host_revision, expected_host_digest):
        with ExitStack() as stack:
            stack.enter_context(self.service.lock)
            stack.enter_context(self.service.bridge._lock)
            principal, current, _, _ = self._scope(
                token=token, project_id=project_id, task_id=task_id,
            )
            self._assert_current(current, expected_host_revision, expected_host_digest)
            base = self._case(current, case_revision=case_revision,
                              case_digest=case_digest)
            return self._safe_result(
                self._read_scoped(base, principal)
            )

    def query_first_status(self, *, token, project_id, task_id,
                           case_revision, case_digest,
                           expected_host_revision, expected_host_digest):
        with ExitStack() as stack:
            stack.enter_context(self.service.lock)
            stack.enter_context(self.service.bridge._lock)
            principal, current, _, _ = self._scope(
                token=token, project_id=project_id, task_id=task_id,
            )
            self._assert_current(current, expected_host_revision, expected_host_digest)
            base = self._case(current, case_revision=case_revision,
                              case_digest=case_digest)
            self._read_scoped(base, principal)
            return self.store.query_first_status(baseline=base, principal=principal)

    def refer_from_trusted_receipt(
        self, *, token, project_id, task_id,
        expected_host_revision, expected_host_digest,
        assignee_username, deadline, reason, missing_fields,
        event_id, occurred_at,
    ):
        """Python-only verified receipt boundary; NO browser receipt argument.

        The optional source is installed by a trusted host operator. It must
        independently authenticate Taraz, not accept browser verification
        flags. Without it this method denies BEFORE a store mutation.
        """
        with ExitStack() as stack:
            stack.enter_context(self.service.lock)
            stack.enter_context(self.service.bridge._lock)
            principal, current, marker, _ = self._scope(
                token=token, project_id=project_id, task_id=task_id,
            )
            if principal.role != "taraz_finance_reviewer":
                raise PermissionError("explicit finance reviewer grant required")
            self._assert_current(current, expected_host_revision, expected_host_digest)
            if self._verified_receipt_source is None:
                raise PermissionError("independent authenticated Taraz receipt unavailable")
            if marker["reviewState"] != "IN_FINANCE_REVIEW":
                raise PermissionError("finance review still pending")
            assignee_name = _id(assignee_username, "assignee")
            account = self.service.users.get(assignee_name)
            target_name, _ = _project_grants(account, project_id)
            if target_name != assignee_name:
                raise PermissionError("assignee account mismatch")
            assignee = Principal(
                user_id=assignee_name, org_id=self.org_id, role="madar_user",
                projects=frozenset({project_id}),
                capabilities=frozenset({_RESOLVE}),
                authenticated=False, active=True,
            )
            # This object is not accepted from a method parameter or JSON.
            receipt = self._verified_receipt_source.verified_receipt_for(
                baseline=current,
            )
            if type(receipt) is not FinanceReceipt or (
                receipt.source != "taraz"
                or receipt.verified_by_adapter is not True
                or receipt.receipt_id != marker["expectedReceiptId"]
                or receipt.generation != marker["receiptGeneration"]
                or receipt.request_id != current.request_id
                or receipt.org_id != current.org_id
                or receipt.project_id != current.project_id
                or receipt.revision != current.revision
                or receipt.digest != current.digest
            ):
                raise PermissionError("independently verified receipt does not match host")
            if type(missing_fields) is not frozenset:
                raise HostDeficiencyError("immutable missing-fields set required")
            review = ReviewCase(
                baseline=current,
                expected_receipt_id=marker["expectedReceiptId"],
                expected_receipt_generation=marker["receiptGeneration"],
                previous_receipt_ids=_names(marker["previousReceiptIds"], "receipts"),
                previous_send_keys=_names(marker["previousSendKeys"], "send keys"),
                review_state=marker["reviewState"],
            )
            result = self.store.refer(
                review, receipt, reviewer=principal, assignee=assignee,
                deadline=_time(deadline), reason=reason,
                missing_fields=missing_fields, event_id=event_id,
                occurred_at=_time(occurred_at),
            )
            return self._safe_result(result)

    def resolve_saved_fields(
        self, *, token, project_id, task_id,
        case_revision, case_digest, expected_case_version,
        expected_host_revision, expected_host_digest,
        corrected_field_names, result_note, event_id, occurred_at,
    ):
        """Only the assignee can resolve fields already saved in host state."""
        with ExitStack() as stack:
            stack.enter_context(self.service.lock)
            stack.enter_context(self.service.bridge._lock)
            principal, current, _, task = self._scope(
                token=token, project_id=project_id, task_id=task_id,
            )
            self._assert_current(current, expected_host_revision, expected_host_digest)
            base = self._case(current, case_revision=case_revision,
                              case_digest=case_digest)
            if (type(corrected_field_names) is not frozenset or
                    not 1 <= len(corrected_field_names) <= 48):
                raise HostDeficiencyError("explicit bounded corrected field names required")
            values = task.get("mtrDeficiencyFields")
            if type(values) is not dict:
                raise PermissionError("saved correction field data missing")
            corrections = {}
            for field in corrected_field_names:
                name = _id(field, "corrected field")
                value = values.get(name)
                if (type(value) is not str or not 1 <= len(value) <= 1000
                        or value != value.strip() or
                        any(ord(c) < 32 for c in value)):
                    raise PermissionError("corrected field not saved or invalid")
                corrections[name] = value
            result = self.store.resolve(
                baseline=base, actor=principal,
                saved_baseline=current, corrections=corrections,
                result_note=result_note, event_id=event_id,
                occurred_at=_time(occurred_at),
                expected_version=expected_case_version,
            )
            return self._safe_result(result)

    def manual_resend_intent(
        self, *, token, project_id, task_id,
        case_revision, case_digest, expected_case_version,
        expected_host_revision, expected_host_digest,
        explicit_manual_action, warning_acknowledged,
        new_send_key, event_id, occurred_at,
    ):
        """Host-CAS-gated metadata intent, NEVER a Taraz send or official post."""
        with ExitStack() as stack:
            stack.enter_context(self.service.lock)
            stack.enter_context(self.service.bridge._lock)
            principal, current, _, _ = self._scope(
                token=token, project_id=project_id, task_id=task_id,
            )
            if principal.role != "taraz_finance_reviewer":
                raise PermissionError("explicit finance resubmission reviewer required")
            if explicit_manual_action is not True:
                raise PermissionError("explicit human resend action required")
            self._assert_current(current, expected_host_revision, expected_host_digest)
            base = self._case(current, case_revision=case_revision,
                              case_digest=case_digest)
            result = self.store.prepare_manual_intent(
                baseline=base, actor=principal,
                current_server_baseline=current,
                server_revalidated=True,  # Set only from locked host snapshot.
                explicit_manual_action=True,
                warning_acknowledged=warning_acknowledged,
                new_send_key=new_send_key, event_id=event_id,
                occurred_at=_time(occurred_at),
                expected_version=expected_case_version,
            )
            return self._safe_result(result)


__all__ = ["DeficiencyHostAdapter", "HostDeficiencyError"]
