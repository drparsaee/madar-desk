"""Host-only E6 notification bridge for a configured Madar LAN service.

Only a host-installed event journal/provider supplies event contents. A caller
can select an event key, list its own inbox, or mark its own notice read. No
socket route, finance/Taraz action, or external delivery is installed here.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re

from mtr_internal_notification_policy import (
    EVENT_KINDS, STATUS_VALUES, plan_internal_notifications,
)
from mtr_internal_notification_store import (
    HostPrincipal, HostRecipientGrant, InternalNotificationStore,
)


_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,179}\Z", re.ASCII)
_HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_FIELDS = {
    "admin": frozenset({"status", "actor_id", "amendment_id", "deficiency_summary"}),
    "editor": frozenset({"status", "actor_id", "amendment_id"}),
    "viewer": frozenset({"status"}),
}
_UNVERIFIED_FINANCE_STATUSES = frozenset({
    "FINANCE_APPROVED", "FINANCE_REJECTED", "OFFICIALLY_POSTED",
})
_MAX_USERS = 1024
_MAX_TASKS = 20000
_MAX_PROJECTS = 5000


def _id(value, label):
    if type(value) is not str or _ID.fullmatch(value) is None:
        raise ValueError(f"Invalid {label}")
    return value


def _sha_task(task):
    try:
        raw = json.dumps(task, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise PermissionError("Saved task cannot be verified") from exc
    if len(raw) > 2_000_000:
        raise PermissionError("Saved task is too large")
    return hashlib.sha256(raw).hexdigest()


def _visible_fields(account):
    """Read host registry private-field caps, never widen beyond LAN role."""
    ceiling = _FIELDS[account["role"]]
    explicit = account.get("internalNotificationFields")
    if explicit is None:
        return ceiling
    if (type(explicit) is not list or len(explicit) > len(ceiling)
            or any(type(value) is not str for value in explicit)
            or len(explicit) != len(set(explicit))
            or not set(explicit) <= ceiling):
        raise PermissionError("Invalid host notification private-field grant")
    return frozenset(explicit)


@dataclass(frozen=True, slots=True)
class TrustedHostNoticeEvent:
    """Immutable event returned by the host's own persisted event provider.

    Constructing this object does not prove event integrity. The injecting
    host must independently authenticate and validate its event journal.
    task_sha256 binds this event to the saved task at publish time.
    """

    event_key: str
    task_id: str
    task_sha256: str
    project_id: str
    original_request_id: str
    event_kind: str
    actor_id: str
    occurred_at: str
    previous_revision: int
    revision: int
    previous_status: str
    status: str
    amendment_id: str | None = None
    assigned_user_id: str | None = None
    deficiency_summary: str | None = None


class MtrLanNotificationAdapter:
    """In-process host adapter; NOT mounted on any existing LAN endpoint.

    `trusted_event_source(key)` is installed by host code, not supplied by a
    remote request. It must fetch an authenticated durable event keyed by its
    identity, reject missing/replaced entries, and return a TrustedHostNoticeEvent.
    The host-owned users registry must explicitly enable internalNotificationsEnabled
    for each recipient; the current LAN account editor does not manage this flag.
    """

    def __init__(self, service, store, *, org_id, trusted_event_source):
        if type(store) is not InternalNotificationStore:
            raise TypeError("InternalNotificationStore required")
        _id(org_id, "organization")
        if (not callable(trusted_event_source)
                or not callable(getattr(service, "account_for", None))
                or not hasattr(service, "lock")
                or not hasattr(getattr(service, "bridge", None), "_lock")
                or not callable(getattr(service.bridge, "getState", None))
                or not hasattr(service, "users")):
            raise TypeError("Authenticated host and trusted event source required")
        self._service = service
        self._store = store
        self._org_id = org_id
        self._trusted_event_source = trusted_event_source

    @staticmethod
    def _projects(state):
        if (type(state) is not dict or type(state.get("projects")) is not list
                or len(state["projects"]) > _MAX_PROJECTS):
            raise PermissionError("Host project state unavailable")
        projects = [_id(p.get("id"), "project") for p in state["projects"]
                    if type(p) is dict]
        if len(projects) != len(state["projects"]) or len(projects) != len(set(projects)):
            raise PermissionError("Invalid host project registry")
        return frozenset(projects)

    @staticmethod
    def _granted(account, projects):
        grants = account.get("projects")
        if grants is None:
            return projects
        if (type(grants) is not list or len(grants) > _MAX_PROJECTS
                or any(type(item) is not str for item in grants)):
            raise PermissionError("Unknown project grant")
        explicit = [_id(item, "project grant") for item in grants]
        if len(explicit) != len(set(explicit)) or not set(explicit) <= projects:
            raise PermissionError("Invalid or stale project grant")
        return frozenset(explicit)

    def _context(self, token):
        if type(token) is not str or not 8 <= len(token) <= 512:
            raise PermissionError("Authenticated LAN session required")
        account = self._service.account_for(token)
        accounts = self._service.users
        if (type(account) is not dict or type(accounts) is not dict
                or len(accounts) > _MAX_USERS):
            raise PermissionError("Host users registry unavailable")
        user_id = _id(account.get("username"), "session user")
        if accounts.get(user_id) is not account or account.get("role") not in _FIELDS:
            raise PermissionError("Session no longer matches a valid host user")
        state = self._service.bridge.getState()
        projects = self._projects(state)
        grants = self._granted(account, projects)
        return account, accounts, state, projects, grants

    @staticmethod
    def _task(state, event, project_ids):
        tasks = state.get("tasks")
        if type(tasks) is not list or len(tasks) > _MAX_TASKS:
            raise PermissionError("Host tasks unavailable")
        matching = [row for row in tasks if type(row) is dict
                    and row.get("id") == event.task_id]
        if len(matching) != 1:
            raise PermissionError("Event task missing or ambiguous")
        task = matching[0]
        if task.get("projectId") != event.project_id or event.project_id not in project_ids:
            raise PermissionError("Event project differs from saved task")
        assignees = task.get("assignees")
        if type(assignees) is not list or len(assignees) > _MAX_USERS:
            raise PermissionError("Saved task assignment unavailable")
        assigned = [_id(user, "assignee") for user in assignees]
        if len(assigned) != len(set(assigned)):
            raise PermissionError("Ambiguous task assignees")
        if event.task_sha256 != _sha_task(task):
            raise PermissionError("Trusted event is stale against saved task")
        return frozenset(assigned)

    @staticmethod
    def _validate_event(event, event_key):
        if type(event) is not TrustedHostNoticeEvent or event.event_key != event_key:
            raise PermissionError("Trusted event source returned unknown event")
        for label in ("event_key", "task_id", "project_id", "original_request_id",
                      "actor_id"):
            _id(getattr(event, label), label)
        if (type(event.task_sha256) is not str
                or _HEX_SHA256.fullmatch(event.task_sha256) is None
                or type(event.event_kind) is not str
                or event.event_kind not in EVENT_KINDS
                or type(event.occurred_at) is not str
                or not 1 <= len(event.occurred_at) <= 80
                or type(event.previous_status) is not str
                or event.previous_status not in STATUS_VALUES
                or type(event.status) is not str
                or event.status not in STATUS_VALUES
                or type(event.previous_revision) is not int
                or type(event.revision) is not int
                or not 0 <= event.previous_revision < event.revision <= 2**63 - 1):
            raise PermissionError("Malformed trusted host event")
        if (event.previous_status in _UNVERIFIED_FINANCE_STATUSES
                or event.status in _UNVERIFIED_FINANCE_STATUSES):
            raise PermissionError("Financial approval/posting provenance unavailable")
        if event.amendment_id is not None:
            _id(event.amendment_id, "amendment")
        if event.assigned_user_id is not None:
            _id(event.assigned_user_id, "assigned user")
        if (event.deficiency_summary is not None
                and (type(event.deficiency_summary) is not str
                     or not 1 <= len(event.deficiency_summary) <= 2000)):
            raise PermissionError("Malformed deficiency summary")
        if event.event_kind == "amendment_status_changed" and event.amendment_id is None:
            raise PermissionError("Missing amendment ID")
        if event.event_kind == "deficiency_assigned" and event.assigned_user_id is None:
            raise PermissionError("Missing assigned user")

    def _principal(self, account, grants, *, publish=False, event_actor=None):
        enabled = account.get("internalNotificationsEnabled") is True
        role = account["role"]
        return HostPrincipal(
            organization_id=self._org_id, user_id=account["username"], role=role,
            readable_project_ids=grants, visible_fields=_visible_fields(account),
            host_verified=True, authenticated=True,
            can_publish=publish, can_read=enabled, can_mark_read=enabled,
            verified_event_actor_id=event_actor,
        )

    def publish(self, token, event_key):
        """Publish an existing host event to current related internal users."""
        _id(event_key, "event key")
        with self._service.lock, self._service.bridge._lock:
            account, accounts, state, projects, grants = self._context(token)
            if account["role"] not in ("admin", "editor"):
                raise PermissionError("Host publisher role required")
            event = self._trusted_event_source(event_key)
            self._validate_event(event, event_key)
            assigned = self._task(state, event, projects)
            if (event.project_id not in grants or
                    (account["role"] != "admin" and account["username"] not in assigned)):
                raise PermissionError("Publisher is not related to this task")
            if event.event_kind == "deficiency_assigned" and event.assigned_user_id not in assigned:
                raise PermissionError("Deficiency assignee is not currently assigned to task")
            actor_account = accounts.get(event.actor_id)
            if (type(actor_account) is not dict
                    or actor_account.get("username") != event.actor_id
                    or actor_account.get("role") not in ("admin", "editor")
                    or event.project_id not in self._granted(actor_account, projects)):
                raise PermissionError("Event actor is not a verified host project editor")
            recipients = []
            host_grants = []
            for user_id, user in sorted(accounts.items()):
                if type(user) is not dict or user.get("username") != user_id:
                    raise PermissionError("Invalid host recipient account")
                role = user.get("role")
                if role not in _FIELDS:
                    raise PermissionError("Unknown host recipient role")
                user_grants = self._granted(user, projects)
                if (user.get("internalNotificationsEnabled") is not True
                        or event.project_id not in user_grants
                        or (role != "admin" and user_id not in assigned)):
                    continue
                fields = _visible_fields(user)
                recipients.append({
                    "organization_id": self._org_id,
                    "user_id": user_id, "role": role,
                    "server_read_authorized": True,
                    "readable_project_ids": [event.project_id],
                    "related_request_ids": [event.original_request_id],
                    "visible_fields": sorted(fields),
                    "internal_notifications_enabled": True,
                })
                host_grants.append(HostRecipientGrant(
                    organization_id=self._org_id, user_id=user_id, role=role,
                    readable_project_ids=frozenset((event.project_id,)),
                    related_request_ids=frozenset((event.original_request_id,)),
                    visible_fields=fields, host_verified=True,
                    notifications_enabled=True,
                ))
            event_data = {
                "organization_id": self._org_id, "project_id": event.project_id,
                "server_read_authorized": True, "server_event_trusted": True,
                "event_key": event.event_key,
                "original_request_id": event.original_request_id,
                "event_kind": event.event_kind, "actor_id": event.actor_id,
                "occurred_at": event.occurred_at,
                "previous_revision": event.previous_revision,
                "revision": event.revision,
                "previous_status": event.previous_status, "status": event.status,
                "amendment_id": event.amendment_id,
                "assigned_user_id": event.assigned_user_id,
                "deficiency_summary": event.deficiency_summary,
            }
            scope = {
                "organization_id": self._org_id, "server_scoped": True,
                "actor_authenticated": True, "actor_authorized": True,
                "actor_id": account["username"], "actor_role": account["role"],
                "readable_project_ids": [event.project_id],
                "visible_fields": sorted(_visible_fields(account)),
                "notify_authorized": True, "dedup_snapshot_trusted": True,
                "authoritative_revision": event.revision,
            }
            # Empty snapshot intentionally: store's atomic per-recipient dedup
            # is the authority. Pre-suppressing keys could hide conflicting data.
            plan = plan_internal_notifications(event_data, recipients, scope=scope,
                                               seen_event_keys=[])
            principal = self._principal(account, grants, publish=True,
                                        event_actor=event.actor_id)
            return self._store.publish_plan(
                plan, principal=principal, project_id=event.project_id,
                recipient_grants=host_grants,
            )

    def list_notifications(self, token, *, project_id=None, limit=100):
        """Recheck session, live role/grants and inbox permission on each read."""
        if project_id is not None:
            _id(project_id, "project")
        with self._service.lock, self._service.bridge._lock:
            account, _, _, _, grants = self._context(token)
            if account.get("internalNotificationsEnabled") is not True:
                raise PermissionError("Internal inbox access not enabled")
            principal = self._principal(account, grants)
            notices = self._store.list_notifications(
                principal=principal, project_id=project_id, limit=limit,
            )
            # Store may also have records from other host writers. Never
            # present unsupported finance decisions as verified status.
            for notice in notices:
                if notice["status"] in _UNVERIFIED_FINANCE_STATUSES:
                    notice["status"] = None
            return notices

    def mark_read(self, token, notice_id):
        """Mark only current authenticated recipient's project notice read."""
        with self._service.lock, self._service.bridge._lock:
            account, _, _, _, grants = self._context(token)
            if account.get("internalNotificationsEnabled") is not True:
                raise PermissionError("Internal inbox access not enabled")
            return self._store.mark_read(notice_id, principal=self._principal(account, grants))


__all__ = ["MtrLanNotificationAdapter", "TrustedHostNoticeEvent"]
