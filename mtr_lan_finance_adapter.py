"""Explicitly mounted MadarHost metadata-only finance request pilot.

NO Taraz transport, official document posting, financial ledger or automatic send.
The trusted organization is injected by the host, never accepted from HTTP JSON.
All card metadata and revisions are derived from the host's saved state while
the host lock is held, not from the client's potentially dirty card data.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json

from mtr_host_request_store import (
    HostRequestStore, StoreConflict, StoreError, TrustedPrincipal,
)
from mtr_account_lineage import principal_actor_id


_ROUTES = frozenset({"prepare", "manual-send", "status"})


class MtrLanFinanceAdapter:
    """Local host API adapter; caller must mount ONLY on the existing TLS LAN server."""

    def __init__(self, service, store: HostRequestStore, *, org_id: str):
        if not isinstance(store, HostRequestStore):
            raise TypeError("HostRequestStore required")
        if (not isinstance(org_id, str) or not 1 <= len(org_id) <= 120
                or any(ord(c) < 33 or ord(c) > 126 for c in org_id)):
            raise ValueError("server-owned organization ID required")
        self.service = service
        self.store = store
        self.org_id = org_id

    @staticmethod
    def _exact(payload, names):
        if type(payload) is not dict or set(payload) != set(names):
            raise ValueError("invalid finance metadata request")

    @staticmethod
    def _task_revision(task):
        """Exact 52-bit revision of the saved card, not an untrusted client counter."""
        try:
            raw = json.dumps(task, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError("saved card cannot be versioned") from exc
        if len(raw) > 2_000_000:
            raise ValueError("saved card exceeds finance metadata revision bound")
        return (int.from_bytes(hashlib.sha256(raw).digest()[:7], "big") >> 4) + 1

    def _principal_and_task(self, token, task_id):
        account = self.service.account_for(token)
        if type(account) is not dict or "projects" not in account:
            raise PermissionError("current private account project scope unavailable")
        if account.get("role") not in ("admin", "editor"):
            raise PermissionError("finance request action denied")
        if account.get("role") != "admin" and account.get("financeEdit") is not True:
            raise PermissionError("finance request action denied")
        if type(task_id) is not str or not 1 <= len(task_id) <= 180:
            raise ValueError("invalid task ID")
        state = self.service.bridge.getState()
        if (type(state) is not dict or type(state.get("tasks")) is not list
                or len(state["tasks"]) > 100000):
            raise PermissionError("current host card registry unavailable")
        matching = [item for item in state["tasks"]
                    if type(item) is dict and item.get("id") == task_id]
        if len(matching) != 1:
            raise PermissionError("task unavailable")
        task = matching[0]
        project_id = task.get("projectId")
        grants = account.get("projects")
        # A grant string is not an iterable allowlist, and an orphaned card
        # cannot give a revoked/deleted project an outbound finance identity.
        # Both registries come from current host-owned state, under the host
        # and bridge locks acquired by handle()/the pilot coordinator.
        active_projects = state.get("projects") if type(state) is dict else None
        if (type(active_projects) is not list or len(active_projects) > 1000
                or any(type(entry) is not dict or
                       type(entry.get("id")) is not str or
                       not 1 <= len(entry["id"]) <= 180 or
                       entry["id"] != entry["id"].strip()
                       for entry in active_projects)):
            raise PermissionError("current project registry unavailable")
        active_ids = [entry["id"] for entry in active_projects]
        if len(set(active_ids)) != len(active_ids):
            raise PermissionError("ambiguous current project registry")
        if grants is not None and (
            type(grants) is not list or len(grants) > 1000 or
            any(type(value) is not str or not 1 <= len(value) <= 180 or
                value != value.strip() for value in grants) or
            len(set(grants)) != len(grants)
        ):
            raise PermissionError("invalid current project grants")
        if (type(project_id) is not str or project_id not in active_ids
                or (grants is not None and project_id not in grants)):
            raise PermissionError("project unavailable")
        title = task.get("title")
        if not isinstance(title, str) or not title.strip() or len(title) > 300:
            raise ValueError("invalid saved card title")
        # Session ID is a non-reversible digest, never the bearer itself.
        # Re-login changes session scope and requires separately reviewed recovery.
        session_id = hashlib.sha256(token.encode("utf-8")).hexdigest()
        permissions = frozenset({"mtr.prepare", "mtr.manual_send", "mtr.read"})
        projects = frozenset({project_id})
        principal = TrustedPrincipal(
            user_id=principal_actor_id(account), org_id=self.org_id,
            session_id=session_id, role=account["role"],
            project_ids=projects, permissions=permissions,
            authenticated=True, session_valid=True,
        )
        return principal, task, self._task_revision(task)

    def _recovery_principal(self, token):
        """Current authenticated host role/project grants, READ capability only.

        An order/card may have changed or disappeared since the first
        authorized send. This does NOT recreate an old session, and cannot
        grant prepare/manual_send permissions. Original ownership and project
        are checked again in HostRequestStore.recovery_snapshot.
        """
        account = self.service.account_for(token)
        if type(account) is not dict or "projects" not in account:
            raise PermissionError("current private account project scope unavailable")
        if type(account) is not dict or account.get("role") not in ("admin", "editor"):
            raise PermissionError("current finance recovery role required")
        if account["role"] == "editor" and account.get("financeEdit") is not True:
            raise PermissionError("current finance recovery capability required")
        username = account.get("username")
        if type(username) is not str or not 1 <= len(username) <= 180:
            raise PermissionError("current finance recovery identity required")
        grants = account.get("projects")
        if grants is not None and (type(grants) is not list or
                len(grants) > 1000 or
                any(type(value) is not str or not value for value in grants) or
                len(set(grants)) != len(grants)):
            raise PermissionError("invalid current project grants")
        state = self.service.bridge.getState()
        projects = state.get("projects") if type(state) is dict else None
        if type(projects) is not list or len(projects) > 1000:
            raise PermissionError("current saved project registry unavailable")
        active = []
        for entry in projects:
            if (type(entry) is not dict or type(entry.get("id")) is not str
                    or not entry["id"]):
                raise PermissionError("invalid saved project registry")
            active.append(entry["id"])
        if len(set(active)) != len(active):
            raise PermissionError("duplicate saved project registry")
        permitted = frozenset(project for project in active
                              if grants is None or project in grants)
        if not permitted:
            raise PermissionError("no current project visibility")
        if type(token) is not str or not token:
            raise PermissionError("authenticated session required")
        return TrustedPrincipal(
            user_id=principal_actor_id(account), org_id=self.org_id,
            session_id=hashlib.sha256(token.encode("utf-8")).hexdigest(),
            role=account["role"], project_ids=permitted,
            permissions=frozenset({"mtr.read"}),
            authenticated=True, session_valid=True,
        )

    def handle(self, action, token, payload):
        """Return status dict after an explicit human UI call, with NO transport.

        This is deliberately restricted to three host operations. In particular,
        no receipt-ingest or pretend-Taraz-authenticated endpoint is exposed.
        """
        if action not in _ROUTES:
            raise ValueError("unsupported finance pilot action")
        if not isinstance(token, str) or not token:
            raise PermissionError("authenticated LAN session required")
        expected = ({"requestId", "taskId", "prepareKey", "manualAction"}
                    if action == "prepare" else
                    {"requestId", "taskId", "sendKey", "payloadSha256",
                     "baseRevision", "manualAction"} if action == "manual-send" else
                    {"requestId", "taskId", "baseRevision"})
        self._exact(payload, expected)
        if action != "status" and payload["manualAction"] is not True:
            raise PermissionError("explicit human action required")
        # Service and bridge locks serialize save-state, role and grant changes
        # against the snapshot and the durable outbox mutation.
        with self.service.lock, self.service.bridge._lock:
            principal, task, revision = self._principal_and_task(token, payload["taskId"])
            request_id = payload["requestId"]
            if action == "prepare":
                try:
                    existing = self.store.request_snapshot(
                        principal=principal, request_id=request_id,
                        expected_base_revision=revision,
                    )
                except KeyError:
                    existing = None
                except StoreConflict:
                    raise
                if existing is not None:
                    former = existing["payload"]
                    if (former["taskId"] != task["id"]
                            or former["projectId"] != task["projectId"]
                            or former["title"] != task["title"]):
                        raise StoreConflict("saved task changed since preparation")
                    proposal = former
                else:
                    proposal = {
                        "schema": 1, "source": "madar", "id": request_id,
                        "taskId": task["id"], "projectId": task["projectId"],
                        "title": task["title"],
                        "createdUtc": datetime.now(timezone.utc).isoformat(),
                    }
                return self.store.prepare_request(
                    principal=principal, request_id=request_id, payload=proposal,
                    base_revision=revision, current_server_revision=revision,
                    prepare_key=payload["prepareKey"], explicit_manual_action=True,
                )
            if action == "manual-send":
                saved = self.store.request_snapshot(
                    principal=principal, request_id=request_id,
                    expected_base_revision=payload["baseRevision"],
                )
                if saved["payload"]["taskId"] != task["id"]:
                    raise PermissionError("request task mismatch")
                return self.store.manual_send(
                    principal=principal, request_id=request_id,
                    expected_payload_sha256=payload["payloadSha256"],
                    expected_base_revision=payload["baseRevision"],
                    current_server_revision=revision, send_key=payload["sendKey"],
                    explicit_manual_action=True,
                )
            saved = self.store.request_snapshot(
                principal=principal, request_id=request_id,
                expected_base_revision=payload["baseRevision"],
            )
            if saved["payload"]["taskId"] != task["id"]:
                raise PermissionError("request task mismatch")
            # Never return stored title or optional financial data on status.
            return {key: saved[key] for key in (
                "requestId", "requestState", "receiptState", "receiptId",
                "sendKey", "nextAction", "transportCalled", "financialEventCreated",
            )}


__all__ = ["MtrLanFinanceAdapter"]
