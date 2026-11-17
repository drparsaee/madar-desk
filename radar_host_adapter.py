"""In-process LAN/Radar E1 adapter. NOT an HTTP route and NOT mounted on LAN.

Contract:
    RadarHostAdapter(lan_service, radar_store, org_id="trusted-host-org")
    adapter.handle(token, command_json_bytes_or_str) -> JSON-safe dict

All commands are schemaVersion 1 and have exactly:
    {"schemaVersion": 1, "action": str, "projectId": str, "params": dict,
     "manualAction": true}       # mutations only
    {"schemaVersion": 1, "action": str, "projectId": str, "params": dict}
                                  # read-only queries only

Mutations: create_contact, update_contact, record_note, schedule_followup,
complete_followup, soft_delete_contact. Reads: get_contact, list_contacts,
list_history, list_due_reminders. Field spellings in params are camelCase.
For writes, params MUST supply an eventId, occurredAt (explicit user-reported
timestamp; NOT a verified host clock), and for existing contacts an
expectedVersion. This timestamp is kept unchanged on retries so that the
underlying store's hash-based idempotency remains stable. A production
integration can issue a durable host timestamp/intent instead.

This adapter NEVER starts a socket, sends customer messages, reaches Taraz,
creates official parties, or posts financial information. Only the host may
construct this object and inject its organization ID and SQLite store path.
The caller is responsible for exposing it ONLY behind the existing separately
validated/authenticated TLS listener. This pilot does not itself test TLS.

Important trust boundaries:
* Neither organization, actor, role, permissions nor assignable members come
  from client JSON. Under LanService.lock then bridge._lock, account_for(token)
  returns the active saved LAN account, and bridge.getState() supplies EXISTING
  project IDs. Current saved LAN accounts supply role and project grants.
* Assignable users are existing active editor/admin accounts in the same host
  registry with membership of the project. The host-owned org_id denotes this
  registry's single organization; production multi-org membership needs an
  independently authenticated tenant registry.
* Capability flags are derived from LAN roles: admin may manage, assign,
  delete; editor may create/edit/record and complete their own CRM follow-ups;
  viewer may only read their own assigned records, never make mutations.
  The RadarCrmStore additionally checks ownership and assignee ACLs and CAS.
* Authentication, authorization, saved projects and the SQLite call execute
  within one host lock order. A later HTTP exposure must apply body/time/
  origin/TLS/rate controls at the server transport. JSON parsing here has a
  strict size ceiling, duplicate-key rejection and no unknown keys.
"""

from __future__ import annotations

import json
import re
from typing import Any

from radar_crm_store import Principal, RadarCrmStore


MAX_COMMAND_BYTES = 8192
MAX_PROJECTS = 1000
MAX_USERS = 1000
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z", re.ASCII)
_MUTATIONS = frozenset((
    "create_contact", "update_contact", "record_note", "schedule_followup",
    "complete_followup", "soft_delete_contact",
))
_READS = frozenset(("get_contact", "list_contacts", "list_history",
                    "list_due_reminders"))
_FIELDS = {
    "create_contact": (
        {"contactId", "eventId", "occurredAt", "name"},
        {"contactDetail", "ownerId", "assigneeId"},
    ),
    "update_contact": (
        {"contactId", "eventId", "occurredAt", "expectedVersion"},
        {"name", "contactDetail", "ownerId", "assigneeId"},
    ),
    "record_note": (
        {"contactId", "eventId", "occurredAt", "expectedVersion", "note"},
        {"channel"},
    ),
    "schedule_followup": (
        {"contactId", "eventId", "occurredAt", "expectedVersion",
         "followupId", "dueAt", "subject"},
        {"assignedTo"},
    ),
    "complete_followup": (
        {"contactId", "eventId", "occurredAt", "expectedVersion",
         "followupId", "outcome"},
        set(),
    ),
    "soft_delete_contact": (
        {"contactId", "eventId", "occurredAt", "expectedVersion"},
        set(),
    ),
    "get_contact": ({"contactId"}, {"includeDeleted"}),
    "list_contacts": (set(), {"afterId", "limit", "includeDeleted"}),
    "list_history": ({"contactId"}, {"afterVersion", "limit"}),
    "list_due_reminders": ({"asOf"}, {"limit"}),
}


class RadarHostAdapterError(ValueError):
    """Safe error code. Contains no tokens, customer IDs or raw JSON."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _deny(condition: bool, code: str) -> None:
    if not condition:
        raise RadarHostAdapterError(code)


def _id(value: object, code: str = "invalid_identifier") -> str:
    _deny(type(value) is str and _ID.fullmatch(value) is not None, code)
    return value


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    record = {}
    for key, value in items:
        _deny(key not in record, "invalid_json")
        record[key] = value
    return record


def _no_constant(_: str):
    raise RadarHostAdapterError("invalid_json")


def _decode(raw: object) -> dict:
    _deny(type(raw) in (str, bytes), "invalid_json")
    try:
        payload = raw.encode("utf-8") if type(raw) is str else raw
        _deny(0 < len(payload) <= MAX_COMMAND_BYTES, "invalid_json")
        command = json.loads(
            payload.decode("utf-8"), object_pairs_hook=_pairs,
            parse_constant=_no_constant,
        )
    except RadarHostAdapterError:
        raise
    except (UnicodeError, TypeError, ValueError, RecursionError) as exc:
        raise RadarHostAdapterError("invalid_json") from exc
    _deny(type(command) is dict, "invalid_command")
    action = command.get("action")
    _deny(type(action) is str and action in _MUTATIONS | _READS,
          "unsupported_action")
    expected = {"schemaVersion", "action", "projectId", "params"}
    if action in _MUTATIONS:
        expected.add("manualAction")
    _deny(set(command) == expected and
          type(command.get("schemaVersion")) is int and
          command["schemaVersion"] == 1, "invalid_command")
    if action in _MUTATIONS:
        _deny(command["manualAction"] is True, "manual_action_required")
    _id(command["projectId"])
    params = command["params"]
    required, optional = _FIELDS[action]
    _deny(type(params) is dict and
          required.issubset(params) and
          set(params).issubset(required | optional), "invalid_params")
    if action == "update_contact":
        _deny(bool(set(params) & optional), "invalid_params")
    # Reject complex payloads. No task, finance, official party data or full
    # records can be tunneled through stringified nested JSON in this schema.
    _deny(all(value is None or type(value) in (str, int, bool)
              for value in params.values()), "invalid_params")
    for field in ("contactId", "eventId", "followupId", "ownerId",
                  "assigneeId", "assignedTo", "afterId"):
        if field in params and params[field] is not None:
            _id(params[field])
    for field in ("expectedVersion", "afterVersion", "limit"):
        if field in params:
            _deny(type(params[field]) is int and
                  0 <= params[field] <= 2**63 - 2, "invalid_params")
    for field in ("includeDeleted",):
        if field in params:
            _deny(type(params[field]) is bool, "invalid_params")
    return command


def _project_snapshot(service: object, account: dict, project_id: str):
    try:
        state = service.bridge.getState()
    except (AttributeError, TypeError, ValueError) as exc:
        raise RadarHostAdapterError("unavailable") from exc
    _deny(type(state) is dict and type(state.get("projects")) is list and
          len(state["projects"]) <= MAX_PROJECTS, "unavailable")
    ids: list[str] = []
    for project in state["projects"]:
        _deny(type(project) is dict, "unavailable")
        ids.append(_id(project.get("id"), "unavailable"))
    _deny(len(ids) == len(set(ids)) and project_id in ids,
          "scope_denied")
    _deny("projects" in account, "scope_denied")
    grants = account.get("projects")
    _deny(grants is None or (
        type(grants) is list and len(grants) <= MAX_PROJECTS and
        all(type(item) is str and _ID.fullmatch(item) for item in grants) and
        len(grants) == len(set(grants))
    ), "scope_denied")
    _deny(grants is None or project_id in grants, "scope_denied")


def _member_grant(account: object, project_id: str) -> bool:
    if type(account) is not dict:
        return False
    if "projects" not in account:
        return False
    if account.get("role") not in ("admin", "editor"):
        return False
    name = account.get("username")
    if type(name) is not str or not _ID.fullmatch(name):
        return False
    grants = account.get("projects")
    return grants is None or (
        type(grants) is list and len(grants) <= MAX_PROJECTS and
        all(type(item) is str and _ID.fullmatch(item) for item in grants) and
        len(grants) == len(set(grants)) and project_id in grants
    )


def _principal(service: object, token: str, org_id: str,
               project_id: str) -> Principal:
    try:
        account = service.account_for(token)
    except PermissionError as exc:
        raise RadarHostAdapterError("authentication_required") from exc
    _deny(type(account) is dict, "authentication_required")
    username = _id(account.get("username"), "authentication_required")
    role = account.get("role")
    _deny(role in ("admin", "editor", "viewer") and type(role) is str,
          "permission_denied")
    _project_snapshot(service, account, project_id)
    accounts = service.users
    _deny(type(accounts) is dict and len(accounts) <= MAX_USERS and
          accounts.get(username) is account and
          all(type(key) is str and type(value) is dict
              for key, value in accounts.items()), "authentication_required")
    members = frozenset(
        name for name, row in accounts.items()
        if type(name) is str and type(row) is dict and
        name == row.get("username") and _member_grant(row, project_id)
    )
    can_edit = role in ("admin", "editor")
    return Principal(
        user_id=username, org_id=org_id,
        project_ids=frozenset((project_id,)),
        assignable_user_ids=members if role == "admin" else frozenset(),
        can_create=can_edit, can_edit=can_edit, can_follow_up=can_edit,
        can_delete=role == "admin", can_manage=role == "admin",
        active=True,
    )


def _read_result(item):
    """Convert immutable store snapshots to JSON-safe detached objects."""
    if isinstance(item, tuple):
        return [_read_result(value) for value in item]
    if hasattr(item, "__dataclass_fields__"):
        # AuditEvent.payload may hold nested MappingProxyType values.
        return {key: _read_result(getattr(item, key))
                for key in item.__dataclass_fields__}
    if hasattr(item, "items"):
        return {key: _read_result(value) for key, value in item.items()}
    return item


class RadarHostAdapter:
    """Host-owned, in-process bridge. No socket/HTTP registration."""

    def __init__(self, service: object, store: RadarCrmStore,
                 *, org_id: str):
        _deny(isinstance(store, RadarCrmStore), "invalid_store")
        _id(org_id, "invalid_org")
        _deny(callable(getattr(service, "account_for", None)) and
              hasattr(service, "lock") and
              hasattr(service, "bridge") and
              hasattr(service.bridge, "_lock") and
              hasattr(service.bridge, "getState") and
              hasattr(service, "users"), "invalid_service")
        self._service = service
        self._store = store
        self._org_id = org_id

    def handle(self, token: str, command_json: bytes | str) -> dict:
        """Evaluate exactly one command with fresh authenticated host scope."""
        _deny(type(token) is str and 8 <= len(token) <= 512,
              "authentication_required")
        command = _decode(command_json)
        action, project_id, params = (
            command["action"], command["projectId"], command["params"]
        )
        # Same ordering as LAN state/role mutations; no stale ACL snapshots.
        with self._service.lock, self._service.bridge._lock:
            p = _principal(self._service, token, self._org_id, project_id)
            if action in _MUTATIONS:
                _deny(p.can_create, "permission_denied")
            common = {"principal": p, "project_id": project_id}
            if action == "create_contact":
                result = self._store.create_contact(
                    **common, contact_id=params["contactId"],
                    event_id=params["eventId"], occurred_at=params["occurredAt"],
                    name=params["name"],
                    **({"contact_detail": params["contactDetail"]}
                       if "contactDetail" in params else {}),
                    **({"owner_id": params["ownerId"]}
                       if "ownerId" in params else {}),
                    **({"assignee_id": params["assigneeId"]}
                       if "assigneeId" in params else {}),
                )
            elif action == "update_contact":
                fields = {"name": "name", "contactDetail": "contact_detail",
                          "ownerId": "owner_id", "assigneeId": "assignee_id"}
                result = self._store.update_contact(
                    **common, contact_id=params["contactId"],
                    event_id=params["eventId"], occurred_at=params["occurredAt"],
                    expected_version=params["expectedVersion"],
                    **{field_name: params[client_name]
                       for client_name, field_name in fields.items()
                       if client_name in params},
                )
            elif action == "record_note":
                result = self._store.record_note(
                    **common, contact_id=params["contactId"],
                    event_id=params["eventId"], occurred_at=params["occurredAt"],
                    expected_version=params["expectedVersion"],
                    note=params["note"], channel=params.get("channel", "other"),
                )
            elif action == "schedule_followup":
                result = self._store.schedule_followup(
                    **common, contact_id=params["contactId"],
                    event_id=params["eventId"], occurred_at=params["occurredAt"],
                    expected_version=params["expectedVersion"],
                    followup_id=params["followupId"], due_at=params["dueAt"],
                    subject=params["subject"],
                    assigned_to=params.get("assignedTo"),
                )
            elif action == "complete_followup":
                result = self._store.complete_followup(
                    **common, contact_id=params["contactId"],
                    event_id=params["eventId"], occurred_at=params["occurredAt"],
                    expected_version=params["expectedVersion"],
                    followup_id=params["followupId"], outcome=params["outcome"],
                )
            elif action == "soft_delete_contact":
                result = self._store.soft_delete_contact(
                    **common, contact_id=params["contactId"],
                    event_id=params["eventId"], occurred_at=params["occurredAt"],
                    expected_version=params["expectedVersion"],
                )
            elif action == "get_contact":
                result = self._store.get_contact(
                    **common, contact_id=params["contactId"],
                    include_deleted=params.get("includeDeleted", False))
            elif action == "list_contacts":
                result = self._store.list_contacts(
                    **common, after_id=params.get("afterId"),
                    limit=params.get("limit", 50),
                    include_deleted=params.get("includeDeleted", False))
            elif action == "list_history":
                result = self._store.list_history(
                    **common, contact_id=params["contactId"],
                    after_version=params.get("afterVersion", 0),
                    limit=params.get("limit", 50))
            else:
                result = self._store.list_due_reminders(
                    **common, as_of=params["asOf"],
                    limit=params.get("limit", 50))
        return {"schemaVersion": 1, "action": action,
                "result": _read_result(result)}


__all__ = ["RadarHostAdapter", "RadarHostAdapterError"]
