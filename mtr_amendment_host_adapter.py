"""E5 host-only pilot. No LAN route, network, Taraz receipt, or finance posting.

The host supplies a valid LanService-like account_for(token), bridge, and
organization. A saved card metadata marker is not a verified Taraz receipt.
"""

from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
import re

from mtr_amendment_store import AmendmentStore, TrustedPrincipal

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z", re.ASCII)
_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}\Z", re.ASCII)
_HEX = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_MAX_COMMAND = 8192
_MAX_STATE_PAIR = 65536
_BASE = frozenset({"action", "projectId", "taskId", "expectedTaskDigest"})
_SHAPES = {
    "create": _BASE | {
        "amendmentId", "proposedFields", "createKey", "acknowledgedOpen",
        "acknowledgedDuplicate", "acknowledgedAt", "previousRejectedAmendmentId",
    },
    "review": _BASE | {
        "amendmentId", "reviewMode", "expectedRowRevision", "chosenValues",
        "operationKey", "occurredAt", "acknowledgedDependencyFields",
        "acknowledgedRevisionChange",
    },
    "manual_unsent_intent": _BASE | {
        "amendmentId", "expectedRowRevision", "sendKey",
        "explicitManualAction", "occurredAt",
    },
    "query": _BASE | {"amendmentId"},
}
_ALL_PERMS = frozenset({
    "mtr.amendment.create", "mtr.amendment.read",
    "mtr.amendment.review", "mtr.amendment.send",
})


class HostCommandError(ValueError):
    """Strict JSON/host snapshot contract failure."""


def _id(value, name, *, operation_key=False):
    if type(value) is not str or not (
        _KEY if operation_key else _ID
    ).fullmatch(value):
        raise HostCommandError("invalid " + name)
    return value


def _unique(pairs):
    result = {}
    for key, val in pairs:
        if key in result:
            raise HostCommandError("duplicate JSON property")
        result[key] = val
    return result


def _bad_number(_):
    raise HostCommandError("invalid nonfinite JSON number")


def _canonical(value, limit):
    try:
        blob = json.dumps(value, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":"), allow_nan=False).encode("utf8")
    except (TypeError, ValueError, RecursionError, UnicodeError) as exc:
        raise HostCommandError("unsafe JSON value") from exc
    if len(blob) > limit:
        raise HostCommandError("JSON too large")
    return blob


def _fields(value, *, allow_empty=False):
    if type(value) is not dict or len(value) > 48 or (
        not allow_empty and not value
    ):
        raise HostCommandError("bounded field map required")
    for key, item in value.items():
        _id(key, "field key")
        if type(item) not in (str, int, bool, type(None)):
            raise HostCommandError("field value must be scalar")
        if type(item) is str and (
            len(item) > 240 or any(ord(c) < 32 for c in item)
        ):
            raise HostCommandError("invalid field text")
        if type(item) is int and abs(item) > 10**15:
            raise HostCommandError("invalid integer field")
    return value


def _parse(command_json):
    if type(command_json) is not str:
        raise HostCommandError("bounded command_json string required")
    try:
        size = len(command_json.encode("utf8"))
    except UnicodeError as exc:
        raise HostCommandError("invalid command Unicode") from exc
    if size > _MAX_COMMAND:
        raise HostCommandError("bounded command_json string required")
    try:
        data = json.loads(command_json, object_pairs_hook=_unique,
                          parse_constant=_bad_number)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise HostCommandError("malformed JSON command") from exc
    if type(data) is not dict or type(data.get("action")) is not str:
        raise HostCommandError("command object/action required")
    action = data["action"]
    if action not in _SHAPES or set(data) != _SHAPES[action]:
        raise HostCommandError("unknown action or unexpected command property")
    _canonical(data, _MAX_COMMAND)
    for name in ("projectId", "taskId", "amendmentId"):
        if name in data:
            _id(data[name], name)
    if type(data["expectedTaskDigest"]) is not str or not _HEX.fullmatch(
        data["expectedTaskDigest"]
    ):
        raise HostCommandError("exact saved task digest required")
    if action == "create":
        _fields(data["proposedFields"])
        _id(data["createKey"], "createKey", operation_key=True)
        if (type(data["acknowledgedOpen"]) is not bool or
                type(data["acknowledgedDuplicate"]) is not bool):
            raise HostCommandError("two explicit warning acknowledgments required")
        if data["previousRejectedAmendmentId"] is not None:
            _id(data["previousRejectedAmendmentId"], "prior amendment")
    elif action == "review":
        if type(data["reviewMode"]) is not str or data["reviewMode"] not in (
            "choose_fields", "re_review_baseline"
        ):
            raise HostCommandError("invalid review mode")
        _fields(data["chosenValues"], allow_empty=True)
        _id(data["operationKey"], "operationKey", operation_key=True)
        dependencies = data["acknowledgedDependencyFields"]
        if (type(dependencies) is not list or len(dependencies) > 48 or
                len(set(_id(item, "dependency") for item in dependencies)) !=
                len(dependencies) or
                type(data["acknowledgedRevisionChange"]) is not bool):
            raise HostCommandError("ambiguous dependency acknowledgment")
        if data["reviewMode"] == "choose_fields" and (
            dependencies or data["acknowledgedRevisionChange"]
        ):
            raise HostCommandError("revision review flags not valid for field choice")
    elif action == "manual_unsent_intent":
        _id(data["sendKey"], "sendKey", operation_key=True)
        if type(data["explicitManualAction"]) is not bool:
            raise HostCommandError("explicit manual action boolean required")
    if action in ("review", "manual_unsent_intent"):
        rev = data["expectedRowRevision"]
        if type(rev) is not int or not 1 <= rev < 2**31:
            raise HostCommandError("invalid expected row revision")
    return data


def _snapshot(state, project_id, task_id):
    """Use only current project/card from bridge.getState under both locks."""
    if type(state) is not dict or type(state.get("projects")) is not list or (
        type(state.get("tasks")) is not list
    ):
        raise PermissionError("trusted state unavailable")
    projects = [p for p in state["projects"] if type(p) is dict and
                p.get("id") == project_id]
    cards = [t for t in state["tasks"] if type(t) is dict and
             t.get("id") == task_id and t.get("projectId") == project_id]
    if len(projects) != 1 or len(cards) != 1:
        raise PermissionError("scoped project/card unavailable")
    project, card = projects[0], cards[0]
    # Hash every saved card/project field, not a client-provided revision.
    digest = hashlib.sha256(_canonical({
        "project": project, "task": card,
    }, _MAX_STATE_PAIR)).hexdigest()
    metadata = card.get("mtrFinanceOriginal")
    if type(metadata) is not dict or set(metadata) != {
        "requestId", "submitted", "fields",
    }:
        raise PermissionError("host card finance-original metadata unavailable")
    _id(metadata["requestId"], "saved original request")
    if metadata["submitted"] is not True:
        raise PermissionError("saved request lacks submission marker")
    original = {
        "requestId": metadata["requestId"], "orgId": "",
        "projectId": project_id, "submitted": True,
        "revision": "task-" + digest[:40],
        "fields": deepcopy(_fields(metadata["fields"])),
    }
    return digest, original


class AmendmentHostAdapter:
    """Host-only interpreter, deliberately not registered with LanService.

    finance_reviewer_usernames is an operator-owned allowlist because the
    existing LAN account roles are admin/editor/viewer, not finance_reviewer.
    Host financeEdit plus this allowlist is required to review or form an
    unsent intent. If the allowlist is empty, both operations always deny.
    """

    def __init__(self, service, store: AmendmentStore, *, org_id,
                 finance_reviewer_usernames: frozenset[str]):
        _id(org_id, "host org")
        if not isinstance(store, AmendmentStore):
            raise HostCommandError("isolated AmendmentStore required")
        if type(finance_reviewer_usernames) is not frozenset or any(
            type(v) is not str or not _ID.fullmatch(v)
            for v in finance_reviewer_usernames
        ):
            raise HostCommandError("explicit host reviewer allowlist required")
        if (not hasattr(service, "lock") or not hasattr(service, "bridge") or
                not hasattr(service.bridge, "_lock") or
                not callable(getattr(service, "account_for", None)) or
                not callable(getattr(service.bridge, "getState", None))):
            raise HostCommandError("authenticated host service/bridge required")
        self.service = service
        self.store = store
        self.org_id = org_id
        self.finance_reviewer_usernames = finance_reviewer_usernames

    def execute(self, *, token, command_json):
        data = _parse(command_json)
        if type(token) is not str or not 32 <= len(token) <= 256 or (
            not token.isascii()
        ):
            raise PermissionError("authenticated LAN token required")
        with ExitStack() as locks:
            locks.enter_context(self.service.lock)
            locks.enter_context(self.service.bridge._lock)
            connection = getattr(self.service.bridge, "connection", None)
            if type(connection) is dict and connection.get("mode") == "client":
                raise PermissionError("host-only adapter cannot use client/offline bridge")
            account = self.service.account_for(token)
            if type(account) is not dict:
                raise PermissionError("authenticated account required")
            name = _id(account.get("username"), "host username")
            role = account.get("role")
            if role not in ("admin", "editor") or (
                role == "editor" and account.get("financeEdit") is not True
            ):
                raise PermissionError("host finance edit grant required")
            grants = account.get("projects")
            project = data["projectId"]
            if role == "admin" and grants is not None:
                raise PermissionError("unexpected administrator project scope")
            if role == "editor" and (
                type(grants) is not list or
                not 1 <= len(grants) <= 500 or
                any(type(item) is not str or not _ID.fullmatch(item)
                    for item in grants) or
                project not in grants or
                len(grants) != len(set(grants))
            ):
                raise PermissionError("explicit project membership required")
            is_reviewer = (
                account.get("financeEdit") is True and
                name in self.finance_reviewer_usernames
            )
            if data["action"] in ("review", "manual_unsent_intent") and (
                not is_reviewer
            ):
                raise PermissionError("explicit host finance reviewer required")
            state = self.service.bridge.getState()
            if (type(state) is dict and
                    (state.get("__offline") is True or
                     state.get("__remoteRevision") == "offline")):
                raise PermissionError("offline/cached client card cannot authorize E5")
            digest, original = _snapshot(state, project, data["taskId"])
            if digest != data["expectedTaskDigest"]:
                raise PermissionError("stale card revision")
            original["orgId"] = self.org_id
            session = "lan-" + hashlib.sha256(
                b"MTR-E5-session-v1\x00" + token.encode("ascii")
            ).hexdigest()[:40]
            principal = TrustedPrincipal(
                user_id=name, org_id=self.org_id, session_id=session,
                role=role, project_ids=frozenset({project}),
                permissions=(
                    _ALL_PERMS if is_reviewer else
                    frozenset({"mtr.amendment.create", "mtr.amendment.read"})
                ),
                authenticated=True, session_valid=True, active=True,
            )
            action = data["action"]
            if action == "create":
                result = self.store.create_amendment(
                    principal=principal, original=original,
                    amendment_id=data["amendmentId"],
                    proposed_fields=data["proposedFields"],
                    create_key=data["createKey"],
                    acknowledged_open=data["acknowledgedOpen"],
                    acknowledged_duplicate=data["acknowledgedDuplicate"],
                    acknowledged_at=data["acknowledgedAt"],
                    previous_rejected_amendment_id=(
                        data["previousRejectedAmendmentId"]
                    ),
                )
            else:
                saved = self.store.get_amendment(
                    principal=principal, amendment_id=data["amendmentId"]
                )
                if saved["originalRequestId"] != original["requestId"]:
                    raise PermissionError("amendment belongs to another saved request")
                if action == "review":
                    opts = dict(
                        principal=principal, amendment_id=data["amendmentId"],
                        expected_row_revision=data["expectedRowRevision"],
                        chosen_values=data["chosenValues"],
                        operation_key=data["operationKey"],
                        occurred_at=data["occurredAt"],
                    )
                    if data["reviewMode"] == "choose_fields":
                        if saved["original"] != original:
                            raise PermissionError("changed card requires re-review")
                        result = self.store.choose_fields(**opts)
                    else:
                        result = self.store.re_review_baseline(
                            current_original=original,
                            acknowledged_dependency_fields=data[
                                "acknowledgedDependencyFields"],
                            acknowledged_revision_change=data[
                                "acknowledgedRevisionChange"],
                            **opts,
                        )
                elif action == "manual_unsent_intent":
                    result = self.store.manual_send_intent(
                        principal=principal, amendment_id=data["amendmentId"],
                        expected_row_revision=data["expectedRowRevision"],
                        current_original=original, send_key=data["sendKey"],
                        explicit_manual_action=data["explicitManualAction"],
                        current_server_verified=True,
                        occurred_at=data["occurredAt"],
                    )
                else:
                    result = saved
            if result.get("sentToTaraz") is not False or (
                result.get("officialFinancePosted") is not False
            ):
                raise RuntimeError("unexpected official finance claim")
            return {
                **result, "hostAuthenticated": True,
                "hostFinanceReviewerAssigned": is_reviewer,
                "tarazReceiptVerified": False,
                "transportState": "NOT_SENT_BY_ADAPTER",
            }
