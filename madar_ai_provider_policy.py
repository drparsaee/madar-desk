"""Pure policy gate for optional local and BYOK cloud AI in Madar Desk.

Version 1 contract (JSON-compatible inputs; no secrets or raw data persisted):

configuration = {
  "schemaVersion": 1, "cloudEnabled": False,
  "enabledProviders": ["local_ollama"],
  "users": {"editor-1": {"aiEnabled": True,
                         "allowedProviders": ["local_ollama"]}},
  "projects": {"project-1": {"allowedProviders": ["local_ollama"]}},
}
request = {
  "schemaVersion": 1, "requestId": "<32 lowercase hex chars>",
  "projectId": "project-1", "provider": "local_ollama",
  "purpose": "task_draft_preview", "contentSource": "user_selected_text",
  "text": "<explicitly selected plain text only>",
}
session = {
  "authenticated": True, "userId": "editor-1", "role": "editor",
  "projectGrants": ["project-1"],
}
runtime = {
  "selectedTextVerified": True, "networkAvailable": False,
  "ephemeralCredentialAvailable": False, "cloudConsentVerified": False,
  "spentCloudRequestIds": [],
}
cloud_consent = {  # only for one explicitly approved cloud request
  "approved": True, "userId": "editor-1", "requestId": request["requestId"],
  "provider": "openai", "textSha256": "<sha256 of exact selected text>",
}

evaluate_ai_request(...) returns a small allow/deny dict. It performs no IO,
model invocation, credential handling, caching, accounting action or network
request. The only permitted payload is text that the authenticated user
explicitly selected for this preview. Fields containing a full task, financial
records, attachments, context, credentials, or fallback lists are rejected.

Security integration obligations for future MadarHost:
* Build session, runtime and consent verification from HOST-AUTHENTICATED state;
  never copy client-supplied booleans or ACLs into these trusted arguments.
* Verify that request.text is exactly the text selected for this send. Pure
  policy cannot prove UI intent or inspect every possible secret in prose.
* On cloud sends, bind an actual user click to user/request/provider/SHA256,
  atomically reserve the unique requestId (or reject if already reserved), and
  consume authorization before dispatch. An untrusted or reused token cannot
  be accepted as cloudConsentVerified. A pure check cannot prevent concurrent
  replays without that host-side atomic reservation.
* Never store or log BYOK secrets here. Resolve an ephemeral key outside this
  module after authorization, and never retry or switch providers automatically.
* Apply data redaction and consent UX before cloud transfer; the conservative
  content filter below detects common finance/credential markers, not every PII
  or confidential phrase. No external send is authorized just by calling this
  pure function; the future transport must enforce this policy again.
"""

from __future__ import annotations

import hashlib
import re


POLICY_VERSION = 1
PROVIDERS = frozenset(("local_ollama", "openai", "gemini", "anthropic"))
CLOUD_PROVIDERS = frozenset(("openai", "gemini", "anthropic"))
MAX_TEXT_BYTES = 8_192
MAX_TEXT_CHARS = 4_000
MAX_USERS = 2_000
MAX_PROJECTS = 2_000
MAX_SPENT_REQUESTS = 10_000

_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z", re.ASCII)
_REQUEST_ID = re.compile(r"[0-9a-f]{32}\Z", re.ASCII)
_DIGEST = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_BIDI = frozenset(("\u202a", "\u202b", "\u202c", "\u202d", "\u202e",
                   "\u2066", "\u2067", "\u2068", "\u2069"))
# Conservative blocklist: prevents *obvious* finance/secret payloads, but is
# not a classifier or a guarantee that text cannot contain private details.
_SENSITIVE = re.compile(
    r"\b(?:iban|swift|bic|account\s*number|bank\s*account|api[_ -]?key"
    r"|bearer|password|access[_ -]?token|private[_ -]?key|ledger"
    r"|invoice|accounting|payroll|banking|financial\s*statement)\b"
    r"|شماره\s*(?:کارت|حساب|شبا)|حساب\s*بانکی|دفتر\s*کل|حسابداری"
    r"|صورت\s*حساب|فاکتور|حقوق\s*و\s*دستمزد|مبلغ|ریال|تومان"
    r"|\bsk-[A-Za-z0-9_-]{12,}\b|AIza[0-9A-Za-z_-]{20,}",
    re.IGNORECASE,
)


class PolicyValidationError(ValueError):
    """Bad shape or value in a provider policy. Includes only a safe code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _check(condition: bool, code: str) -> None:
    if not condition:
        raise PolicyValidationError(code)


def _record(value: object, keys: tuple[str, ...], code: str) -> dict:
    _check(type(value) is dict and set(value) == set(keys), code)
    return value


def _identifier(value: object, code: str) -> str:
    _check(type(value) is str and _IDENTIFIER.fullmatch(value) is not None, code)
    return value


def _providers(value: object, code: str) -> tuple[str, ...]:
    _check(type(value) is list and len(value) <= len(PROVIDERS), code)
    _check(all(type(item) is str and item in PROVIDERS for item in value), code)
    _check(len(value) == len(set(value)), code)
    return tuple(value)


def _grants(value: object) -> tuple[str, ...]:
    _check(type(value) is list and len(value) <= MAX_PROJECTS, "invalid_session")
    grants = tuple(_identifier(item, "invalid_session") for item in value)
    _check(len(grants) == len(set(grants)), "invalid_session")
    return grants


def validate_provider_configuration(config: object) -> dict:
    """Validate and copy the admin-supplied policy; no credentials are accepted.

    Cloud is denied unless cloudEnabled is *explicitly* true and that provider
    is globally enabled and present in both user and project allowlists.
    """
    config = _record(
        config,
        ("schemaVersion", "cloudEnabled", "enabledProviders", "users", "projects"),
        "invalid_configuration",
    )
    _check(type(config["schemaVersion"]) is int and
           config["schemaVersion"] == POLICY_VERSION, "invalid_configuration")
    _check(type(config["cloudEnabled"]) is bool, "invalid_configuration")
    global_providers = _providers(config["enabledProviders"],
                                  "invalid_configuration")
    users = config["users"]
    projects = config["projects"]
    _check(type(users) is dict and len(users) <= MAX_USERS,
           "invalid_configuration")
    _check(type(projects) is dict and len(projects) <= MAX_PROJECTS,
           "invalid_configuration")
    clean_users = {}
    for user_id, value in users.items():
        _identifier(user_id, "invalid_configuration")
        entry = _record(value, ("aiEnabled", "allowedProviders"),
                        "invalid_configuration")
        _check(type(entry["aiEnabled"]) is bool, "invalid_configuration")
        clean_users[user_id] = {
            "aiEnabled": entry["aiEnabled"],
            "allowedProviders": list(_providers(entry["allowedProviders"],
                                               "invalid_configuration")),
        }
    clean_projects = {}
    for project_id, value in projects.items():
        _identifier(project_id, "invalid_configuration")
        entry = _record(value, ("allowedProviders",), "invalid_configuration")
        clean_projects[project_id] = {
            "allowedProviders": list(_providers(entry["allowedProviders"],
                                               "invalid_configuration")),
        }
    return {
        "schemaVersion": POLICY_VERSION,
        "cloudEnabled": config["cloudEnabled"],
        "enabledProviders": list(global_providers),
        "users": clean_users,
        "projects": clean_projects,
    }


def _request(request: object) -> dict:
    request = _record(
        request,
        ("schemaVersion", "requestId", "projectId", "provider", "purpose",
         "contentSource", "text"),
        "invalid_request",
    )
    _check(type(request["schemaVersion"]) is int and
           request["schemaVersion"] == POLICY_VERSION, "invalid_request")
    _check(type(request["requestId"]) is str and
           _REQUEST_ID.fullmatch(request["requestId"]) is not None,
           "invalid_request")
    _identifier(request["projectId"], "invalid_request")
    _check(type(request["provider"]) is str and request["provider"] in PROVIDERS,
           "invalid_request")
    _check(request["purpose"] == "task_draft_preview" and
           type(request["purpose"]) is str, "invalid_request")
    _check(request["contentSource"] == "user_selected_text" and
           type(request["contentSource"]) is str, "privacy_scope_denied")
    value = request["text"]
    _check(type(value) is str and 0 < len(value) <= MAX_TEXT_CHARS and
           bool(value.strip()), "invalid_text")
    _check(not any((ord(char) < 32 and char not in "\n\r\t") or
                   ord(char) == 127 or char in _BIDI for char in value),
           "invalid_text")
    try:
        encoded = value.encode("utf-8")
    except UnicodeError as exc:
        raise PolicyValidationError("invalid_text") from exc
    _check(len(encoded) <= MAX_TEXT_BYTES, "invalid_text")
    # No full task/finance JSON is accepted as merely a "selected text".
    _check(not value.lstrip().startswith(("{", "[")) and
           _SENSITIVE.search(value) is None, "privacy_scope_denied")
    return request


def _session(session: object) -> tuple[str, bool, str, tuple[str, ...]]:
    session = _record(
        session, ("authenticated", "userId", "role", "projectGrants"),
        "invalid_session",
    )
    _check(type(session["authenticated"]) is bool, "invalid_session")
    user_id = _identifier(session["userId"], "invalid_session")
    _check(type(session["role"]) is str and
           session["role"] in ("admin", "editor", "viewer"), "invalid_session")
    return (user_id, session["authenticated"], session["role"],
            _grants(session["projectGrants"]))


def _runtime(runtime: object) -> dict:
    runtime = _record(
        runtime,
        ("selectedTextVerified", "networkAvailable",
         "ephemeralCredentialAvailable", "cloudConsentVerified",
         "spentCloudRequestIds"),
        "invalid_runtime",
    )
    for key in ("selectedTextVerified", "networkAvailable",
                "ephemeralCredentialAvailable", "cloudConsentVerified"):
        _check(type(runtime[key]) is bool, "invalid_runtime")
    used = runtime["spentCloudRequestIds"]
    _check(type(used) is list and len(used) <= MAX_SPENT_REQUESTS,
           "invalid_runtime")
    _check(all(type(item) is str and _REQUEST_ID.fullmatch(item)
               is not None for item in used), "invalid_runtime")
    _check(len(used) == len(set(used)), "invalid_runtime")
    return runtime


def _consent(value: object, *, user_id: str, request: dict, digest: str) -> None:
    value = _record(
        value, ("approved", "userId", "requestId", "provider", "textSha256"),
        "invalid_cloud_consent",
    )
    _check(value["approved"] is True and value["userId"] == user_id and
           value["requestId"] == request["requestId"] and
           value["provider"] == request["provider"] and
           type(value["textSha256"]) is str and
           _DIGEST.fullmatch(value["textSha256"]) is not None and
           value["textSha256"] == digest, "invalid_cloud_consent")


def _decision(allowed: bool, reason: str, provider: str | None = None,
              digest: str | None = None) -> dict:
    """No full text, credential, user identity or finance data in results."""
    return {
        "policyVersion": POLICY_VERSION,
        "allowed": allowed,
        "reason": reason,
        "provider": provider if provider in PROVIDERS else None,
        "textSha256": digest if allowed else None,
        "requiresHumanReview": True,
    }


def evaluate_ai_request(
    configuration: object,
    request: object,
    *,
    session: object,
    runtime: object,
    cloud_consent: object = None,
) -> dict:
    """Return a pure, deny-by-default decision; this function NEVER sends data.

    For cloud, require globally enabled provider, individual user/project
    grants, fresh verified one-send consent tied to requestId and text hash,
    a host-verified ephemeral BYOK credential and online status. No provider
    fallback, paid call, credential persistence or financial action occurs.
    """
    try:
        config = validate_provider_configuration(configuration)
        requested = _request(request)
        user_id, authenticated, role, grants = _session(session)
        state = _runtime(runtime)
    except PolicyValidationError as error:
        return _decision(False, error.code)
    provider = requested["provider"]
    project = requested["projectId"]
    if not authenticated:
        return _decision(False, "unauthenticated", provider)
    if role not in ("admin", "editor"):
        return _decision(False, "role_denied", provider)
    if project not in grants:
        return _decision(False, "project_denied", provider)
    user_policy = config["users"].get(user_id)
    if user_policy is None or user_policy["aiEnabled"] is not True:
        return _decision(False, "user_denied", provider)
    project_policy = config["projects"].get(project)
    if project_policy is None:
        return _decision(False, "project_denied", provider)
    if provider not in config["enabledProviders"]:
        return _decision(False, "provider_disabled", provider)
    if provider not in user_policy["allowedProviders"]:
        return _decision(False, "user_provider_denied", provider)
    if provider not in project_policy["allowedProviders"]:
        return _decision(False, "project_provider_denied", provider)
    if not state["selectedTextVerified"]:
        return _decision(False, "selection_not_verified", provider)
    digest = hashlib.sha256(requested["text"].encode("utf-8")).hexdigest()
    if provider == "local_ollama":
        if cloud_consent is not None:
            return _decision(False, "unexpected_cloud_consent", provider)
        return _decision(True, "allowed_local", provider, digest)
    if not config["cloudEnabled"]:
        return _decision(False, "cloud_disabled", provider)
    if not state["networkAvailable"]:
        return _decision(False, "offline", provider)
    if not state["ephemeralCredentialAvailable"]:
        return _decision(False, "credential_unavailable", provider)
    if not state["cloudConsentVerified"]:
        return _decision(False, "cloud_consent_not_verified", provider)
    if requested["requestId"] in state["spentCloudRequestIds"]:
        return _decision(False, "cloud_consent_reused", provider)
    try:
        _consent(cloud_consent, user_id=user_id, request=requested, digest=digest)
    except PolicyValidationError as error:
        return _decision(False, error.code, provider)
    return _decision(True, "allowed_cloud", provider, digest)
