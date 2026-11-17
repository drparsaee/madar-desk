"""E1 AI-budget host adapter: in-process authorization, NO AI dispatch.

    adapter = MadarAiUsageHostAdapter(lan_service, usage_store,
                                       org_id="host-owned-tenant",
                                       identity_key=host_private_32_byte_key)
    adapter.handle(session_token, command_json_bytes_or_str) -> JSON-safe dict

JSON v1 has exactly schemaVersion, action, projectId, data and, for
mutations, manualAction:true.  Actions:

  grant_get        {userId, provider}                     admin only
  grant_set        {userId, provider, enabled, cloudEnabled,
                    monthlyRequests, monthlyTokens, monthlyCostMicro,
                    expectedVersion, eventId, expiresAtUtc?} admin only
  cloud_consent    {requestId, provider, payloadDigest, eventId}
  consent_revoke   {requestId, eventId}
  reserve          {requestId, provider, payloadDigest,
                    estimatedTokens, maxCostMicro, eventId}
  usage_get        {provider}
  reservation_get  {requestId}

The host owns org_id, clock, account_for(token), saved project list and
current LAN user/role/project grants. None come from client JSON. All calls
run under service.lock + bridge._lock; store writes run under SQLite
BEGIN IMMEDIATE with CAS and idempotency. For duplicate event IDs, the
original immutable host timestamp is recovered from the store's audit log
so exact retries are stable across adapter restarts.

Cloud consent is a *recorded user intent*, NOT proof that the selected text
was safe or genuinely selected. Its digest is accepted as an unverified
opaque client claim: a future host-selected-text preflight must verify the
content and bind a host-keyed digest before permitting any transport.
The adapter mints a transient request-bound approval capability only during
an authenticated, explicit command. Strict cloud provider + digest + request
binding and consent consumption are enforced by the existing usage store.

This adapter intentionally exposes NO mark_dispatched, complete, cancel,
refund, inference, API-key, model-download, provider transport or fallback
action. A successful reservation is NOT permission to send or spend money.
Manual order entry is outside the adapter and remains available when AI is
off. It neither mounts a network route nor starts a server. A production
router must separately enforce authenticated TLS, origin/CSRF, request-rate
limits, reliable host time, data-scope checking and spend reconciliation.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import re
from typing import Any, Callable

from lan import LanService
from madar_ai_usage_store import AiPrincipal, AiUsageStore, AiUsageError


_MAX_JSON_BYTES = 4096
_MAX_PROJECTS = 1000
_MAX_USERS = 1000
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z", re.ASCII)
_REQUEST_ID = re.compile(r"[0-9a-f]{32}\Z", re.ASCII)
_DIGEST = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z", re.ASCII)
_PROVIDERS = frozenset(("local_ollama", "openai", "gemini", "anthropic"))
_CLOUD = _PROVIDERS - {"local_ollama"}
_WRITE_ACTIONS = frozenset(("grant_set", "cloud_consent",
                            "consent_revoke", "reserve"))
_READ_ACTIONS = frozenset(("grant_get", "usage_get", "reservation_get"))
_SCHEMAS = {
    "grant_get": ({"userId", "provider"}, set()),
    "grant_set": (
        {"userId", "provider", "enabled", "cloudEnabled",
         "monthlyRequests", "monthlyTokens", "monthlyCostMicro",
         "expectedVersion", "eventId"},
        {"expiresAtUtc"},
    ),
    "cloud_consent": (
        {"requestId", "provider", "payloadDigest", "eventId"}, set()),
    "consent_revoke": ({"requestId", "eventId"}, set()),
    "reserve": (
        {"requestId", "provider", "payloadDigest", "estimatedTokens",
         "maxCostMicro", "eventId"}, set()),
    "usage_get": ({"provider"}, set()),
    "reservation_get": ({"requestId"}, set()),
}
_EVENT_KINDS = {
    "grant_set": "grant_set",
    "cloud_consent": "cloud_consent",
    "consent_revoke": "consent_revoked",
    "reserve": "reserve",
}


class AiUsageHostError(ValueError):
    """Stable safe error code: no customer data, token or raw request text."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise AiUsageHostError(code)


def _id(value: object, code: str = "invalid_command") -> str:
    _require(type(value) is str and _ID.fullmatch(value) is not None, code)
    return value


def _json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in data, "invalid_json")
        data[key] = value
    return data


def _bad_constant(value: str) -> None:
    raise AiUsageHostError("invalid_json")


def _command(raw: bytes | str) -> dict:
    _require(type(raw) in (bytes, str), "invalid_json")
    try:
        encoded = raw.encode("utf-8") if type(raw) is str else raw
        _require(0 < len(encoded) <= _MAX_JSON_BYTES, "invalid_json")
        data = json.loads(
            encoded.decode("utf-8"), object_pairs_hook=_json_pairs,
            parse_constant=_bad_constant,
        )
    except AiUsageHostError:
        raise
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise AiUsageHostError("invalid_json") from exc
    _require(type(data) is dict, "invalid_command")
    action = data.get("action")
    _require(type(action) is str and action in (_READ_ACTIONS | _WRITE_ACTIONS),
             "unsupported_action")
    expected = {"schemaVersion", "action", "projectId", "data"}
    if action in _WRITE_ACTIONS:
        expected.add("manualAction")
    _require(set(data) == expected and type(data.get("schemaVersion")) is int
             and data["schemaVersion"] == 1, "invalid_command")
    if action in _WRITE_ACTIONS:
        _require(data["manualAction"] is True, "manual_action_required")
    _id(data["projectId"])
    required, optional = _SCHEMAS[action]
    args = data["data"]
    _require(type(args) is dict and required.issubset(args)
             and set(args).issubset(required | optional), "invalid_data")
    for key, value in args.items():
        if key in {"userId", "eventId"}:
            _id(value)
        elif key == "provider":
            _require(type(value) is str and value in _PROVIDERS,
                     "invalid_provider")
        elif key == "requestId":
            _require(type(value) is str and _REQUEST_ID.fullmatch(value)
                     is not None, "invalid_request_id")
        elif key == "payloadDigest":
            _require(type(value) is str and _DIGEST.fullmatch(value)
                     is not None, "invalid_digest")
        elif key in {"enabled", "cloudEnabled"}:
            _require(type(value) is bool, "invalid_data")
        elif key in {"monthlyRequests", "monthlyTokens", "monthlyCostMicro",
                     "expectedVersion", "estimatedTokens", "maxCostMicro"}:
            _require(type(value) is int and 0 <= value <= 10**12,
                     "invalid_data")
        elif key == "expiresAtUtc":
            _require(value is None or
                     (type(value) is str and _UTC.fullmatch(value) is not None),
                     "invalid_data")
        else:
            raise AiUsageHostError("invalid_data")
    return data


def _valid_scope(account: dict, project_id: str) -> None:
    _require("projects" in account, "scope_denied")
    grants = account["projects"]
    _require(grants is None or (
        type(grants) is list and len(grants) <= 500
        and all(type(x) is str and _ID.fullmatch(x) for x in grants)
        and len(set(grants)) == len(grants)
    ), "scope_denied")
    _require(grants is None or project_id in grants, "scope_denied")


def _opaque(identity_key: bytes, org_id: str, namespace: str,
            value: str, *, short: bool = False) -> str:
    """Stable host-keyed pseudonym. None of these raw IDs enter SQLite."""
    raw = f"madar-ai-v1\x00{namespace}\x00{org_id}\x00{value}".encode("utf-8")
    digest = hmac.new(identity_key, raw, hashlib.sha256).hexdigest()
    return digest[:32] if short else digest


def _principal(service: LanService, token: str, org_id: str,
               project_id: str, action: str, target: str | None,
               identity_key: bytes) -> AiPrincipal:
    try:
        account = service.account_for(token)
    except PermissionError as exc:
        raise AiUsageHostError("authentication_required") from exc
    _require(type(account) is dict, "authentication_required")
    user = _id(account.get("username"), "authentication_required")
    role = account.get("role")
    _require(type(role) is str and role in ("admin", "editor", "viewer"),
             "permission_denied")
    accounts = service.users
    _require(type(accounts) is dict and len(accounts) <= _MAX_USERS
             and accounts.get(user) is account
             and all(type(key) is str and type(val) is dict
                     for key, val in accounts.items()), "authentication_required")
    state = service.bridge.getState()
    _require(type(state) is dict and type(state.get("projects")) is list
             and len(state["projects"]) <= _MAX_PROJECTS, "scope_denied")
    project_names = []
    for item in state["projects"]:
        _require(type(item) is dict, "scope_denied")
        project_names.append(_id(item.get("id"), "scope_denied"))
    _require(len(project_names) == len(set(project_names))
             and project_id in project_names, "scope_denied")
    _valid_scope(account, project_id)

    if action in ("grant_get", "grant_set"):
        _require(role == "admin", "permission_denied")
    else:
        _require(role in ("admin", "editor")
                 and account.get("aiEnabled") is True,
                 "ai_disabled")
    permitted = set()
    if role == "admin":
        for username, other in accounts.items():
            _require(type(username) is str and
                     _ID.fullmatch(username) is not None,
                     "authentication_required")
            _require(other.get("username") == username, "authentication_required")
            if other.get("role") in ("admin", "editor"):
                try:
                    _valid_scope(other, project_id)
                except AiUsageHostError:
                    continue
                permitted.add(username)
        if target is not None:
            _require(target in permitted, "target_denied")
    return AiPrincipal(
        user_id=_opaque(identity_key, org_id, "user", user),
        org_id=_opaque(identity_key, org_id, "org", org_id),
        project_ids=frozenset((
            _opaque(identity_key, org_id, "project", project_id),)),
        role=role, authenticated=True, active=True,
        manageable_user_ids=frozenset(
            _opaque(identity_key, org_id, "user", name)
            for name in permitted) if role == "admin"
        else frozenset(),
    )


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if is_dataclass(value):
        return {field.name: _json_safe(getattr(value, field.name))
                for field in fields(value)}
    if isinstance(value, (tuple, list)):
        return [_json_safe(x) for x in value]
    if type(value) is dict:
        return {key: _json_safe(item) for key, item in value.items()}
    return value


class MadarAiUsageHostAdapter:
    """Authenticated in-process budget manager; no dispatcher or listener."""

    def __init__(
        self, service: LanService, store: AiUsageStore, *,
        org_id: str,
        identity_key: bytes,
        clock: Callable[[], datetime] | None = None,
    ):
        _require(isinstance(service, LanService), "invalid_service")
        _require(isinstance(store, AiUsageStore), "invalid_store")
        _id(org_id, "invalid_organization")
        _require(type(identity_key) is bytes and
                 32 <= len(identity_key) <= 256, "invalid_identity_key")
        _require(callable(getattr(service, "account_for", None))
                 and hasattr(service, "lock") and
                 hasattr(service, "bridge") and
                 hasattr(service.bridge, "_lock") and
                 hasattr(service.bridge, "getState"),
                 "invalid_service")
        _require(clock is None or callable(clock), "invalid_clock")
        self._service = service
        self._store = store
        self._org_id = org_id
        self._identity_key = identity_key
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def _timestamp(self) -> str:
        instant = self._clock()
        _require(type(instant) is datetime and instant.tzinfo is not None
                 and instant.utcoffset() is not None, "invalid_clock")
        return instant.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _event_time(self, principal: AiPrincipal, project_id: str,
                    event_id: str, kind: str, now: str) -> str:
        """Reuse immutable server time for an EXACT replay, even after restart."""
        with self._store._connect() as db:
            row = db.execute(
                "SELECT actor, project, kind, occurred FROM ai_audit"
                " WHERE org=? AND event_id=?",
                (principal.org_id, event_id),
            ).fetchone()
        if row is None:
            return now
        _require(row["actor"] == principal.user_id
                 and row["project"] == project_id and row["kind"] == kind,
                 "event_conflict")
        return row["occurred"]

    def handle(self, token: str, command_json: bytes | str) -> dict:
        _require(type(token) is str and 8 <= len(token) <= 512,
                 "authentication_required")
        cmd = _command(command_json)
        action, project, args = cmd["action"], cmd["projectId"], cmd["data"]
        # The authenticated host echoes the exact admin grant target, so a
        # client can reject a valid-looking response for another user/project.
        # This is *response routing* evidence, not proof of cloud consent or
        # authorization without the authenticated command/host boundary.
        grant_scope = ({
            "projectId": project,
            "userId": args["userId"],
            "provider": args["provider"],
        } if action in ("grant_get", "grant_set") else None)
        # Match LAN's authorization/save-state lock ordering. Every request
        # reads a FRESH session, grant and current saved project registry.
        with self._service.lock, self._service.bridge._lock:
            p = _principal(self._service, token, self._org_id, project, action,
                           args.get("userId"), self._identity_key)
            scoped_project = next(iter(p.project_ids))
            scoped_args = dict(args)
            if "userId" in args:
                scoped_args["userId"] = _opaque(
                    self._identity_key, self._org_id, "user", args["userId"])
            if "requestId" in args:
                scoped_args["requestId"] = _opaque(
                    self._identity_key, self._org_id, "request",
                    args["requestId"], short=True)
            if "eventId" in args:
                scoped_args["eventId"] = _opaque(
                    self._identity_key, self._org_id, "event", args["eventId"])
            if "payloadDigest" in args:
                scoped_args["payloadDigest"] = _opaque(
                    self._identity_key, self._org_id, "digest",
                    args["payloadDigest"])
            args = scoped_args
            now = self._timestamp()
            common = {"principal": p, "project_id": scoped_project}

            def timestamp_for_event() -> str:
                return self._event_time(
                    p, scoped_project, args["eventId"],
                    _EVENT_KINDS[action], now)

            if action == "grant_get":
                result = self._store.get_grant(
                    **common, user_id=args["userId"], provider=args["provider"])
            elif action == "grant_set":
                instant = timestamp_for_event()
                result = self._store.set_grant(
                    **common, user_id=args["userId"],
                    provider=args["provider"], enabled=args["enabled"],
                    cloud_enabled=args["cloudEnabled"],
                    monthly_requests=args["monthlyRequests"],
                    monthly_tokens=args["monthlyTokens"],
                    monthly_cost_micro=args["monthlyCostMicro"],
                    expected_version=args["expectedVersion"],
                    event_id=args["eventId"], at_utc=instant,
                    expires_at_utc=args.get("expiresAtUtc"),
                )
            elif action == "cloud_consent":
                instant = timestamp_for_event()
                # This capability exists only inside this authenticated
                # synchronous call, never in client JSON.
                p = AiPrincipal(
                    user_id=p.user_id, org_id=p.org_id,
                    project_ids=p.project_ids, role=p.role,
                    authenticated=p.authenticated, active=p.active,
                    manageable_user_ids=p.manageable_user_ids,
                    approved_cloud_request_ids=frozenset((args["requestId"],)),
                )
                expiry = (
                    datetime.strptime(instant, "%Y-%m-%dT%H:%M:%SZ")
                    .replace(tzinfo=timezone.utc) + timedelta(minutes=5)
                ).strftime("%Y-%m-%dT%H:%M:%SZ")
                result = self._store.grant_cloud_consent(
                    principal=p, project_id=scoped_project,
                    provider=args["provider"], request_id=args["requestId"],
                    payload_digest=args["payloadDigest"],
                    expires_at_utc=expiry, explicit_human_consent=True,
                    event_id=args["eventId"], at_utc=instant,
                )
            elif action == "consent_revoke":
                result = self._store.revoke_cloud_consent(
                    **common, request_id=args["requestId"],
                    event_id=args["eventId"], at_utc=timestamp_for_event(),
                )
            elif action == "reserve":
                instant = timestamp_for_event()
                # Reservations are only bookkeeping. No dispatch API exposed.
                result = self._store.reserve(
                    **common, request_id=args["requestId"],
                    provider=args["provider"],
                    payload_digest=args["payloadDigest"],
                    estimated_tokens=args["estimatedTokens"],
                    max_cost_micro=args["maxCostMicro"],
                    event_id=args["eventId"], at_utc=instant,
                )
            elif action == "usage_get":
                result = self._store.usage(
                    **common, provider=args["provider"], at_utc=now)
            elif action == "reservation_get":
                result = self._store.read_reservation(
                    **common, request_id=args["requestId"])
            else:
                raise AiUsageHostError("unsupported_action")
        response = {"schemaVersion": 1, "action": action,
                    "result": _json_safe(result)}
        if grant_scope is not None:
            response["grantScope"] = grant_scope
        return response


__all__ = ["MadarAiUsageHostAdapter", "AiUsageHostError"]
