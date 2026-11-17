"""E1 AI-budget host integration: synthetic LanService and disposable SQLite."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from pathlib import Path
import socket
import sqlite3
from tempfile import TemporaryDirectory
from threading import Barrier, RLock
import time
import unittest
from unittest.mock import patch

from lan import LanService, make_account
from madar_ai_usage_store import AiUsageError, AiUsageStore
from madar_ai_usage_host_adapter import AiUsageHostError, MadarAiUsageHostAdapter


NOW = datetime(2026, 11, 9, 19, 0, tzinfo=timezone.utc)
RID = "a" * 32
DIGEST = "c" * 64


class MemoryBridge:
    def __init__(self):
        self._lock = RLock()
        self.saved = {
            "projects": [{"id": "project-one"}, {"id": "project-two"}],
            "tasks": [],
        }

    def getState(self):
        return deepcopy(self.saved)


class AiUsageHostAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.accounts = {
            "owner": make_account("owner", "synthetic-owner-password", "admin"),
            "editor": make_account(
                "editor", "synthetic-editor-password", "editor", ["project-one"]),
            "sibling": make_account(
                "sibling", "synthetic-sibling-password", "editor", ["project-two"]),
            "viewer": make_account(
                "viewer", "synthetic-viewer-password", "viewer", ["project-one"]),
        }
        for account in cls.accounts.values():
            account["aiEnabled"] = account["role"] == "editor"

    def setUp(self):
        self.temp = TemporaryDirectory(prefix="synthetic-ai-host-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bridge = MemoryBridge()
        self.service = LanService(self.bridge, self.root / "users.json",
                                  bind="127.0.0.1", port=0)
        self.service.users = deepcopy(self.accounts)
        self.service._store_users()
        self.tokens = {}
        for name in self.service.users:
            token = f"synthetic-test-token-{name}"
            self.tokens[name] = token
            self.service.sessions[token] = (name, time.time() + 3600)
        self.store = AiUsageStore(self.root / "usage.sqlite")
        self.instant = NOW
        self.identity_key = b"synthetic-only-host-hmac-key-32-bytes-long"
        self.adapter = MadarAiUsageHostAdapter(
            self.service, self.store, org_id="org-a",
            identity_key=self.identity_key,
            clock=lambda: self.instant,
        )

    def db_request_id(self, request=RID, *, org="org-a"):
        raw = f"madar-ai-v1\x00request\x00{org}\x00{request}".encode()
        return hmac.new(self.identity_key, raw, hashlib.sha256).hexdigest()[:32]

    def command(self, action, data, *, project="project-one", human=True):
        envelope = {
            "schemaVersion": 1, "action": action, "projectId": project,
            "data": data,
        }
        if action in ("grant_set", "cloud_consent", "consent_revoke", "reserve"):
            envelope["manualAction"] = human
        return envelope

    def send(self, name, command):
        return self.adapter.handle(
            self.tokens[name],
            json.dumps(command, ensure_ascii=False,
                       separators=(",", ":")).encode("utf-8"),
        )

    def denies(self, expected_code, name, command):
        with self.assertRaises((AiUsageHostError, AiUsageError)) as caught:
            self.send(name, command)
        self.assertEqual(getattr(caught.exception, "code", None),
                         expected_code, repr(caught.exception))
        self.assertNotIn("org-b", str(caught.exception))

    def grant(self, *, provider="local_ollama", enabled=True,
              cloud=False, user="editor", requests=2, tokens=500,
              cost=0, version=0, event="set-grant-1", expires=None):
        payload = {
            "userId": user, "provider": provider, "enabled": enabled,
            "cloudEnabled": cloud, "monthlyRequests": requests,
            "monthlyTokens": tokens, "monthlyCostMicro": cost,
            "expectedVersion": version, "eventId": event,
        }
        if expires is not None:
            payload["expiresAtUtc"] = expires
        return self.send("owner", self.command("grant_set", payload))

    def consent(self, *, request=RID, provider="openai", digest=DIGEST,
                event="cloud-consent-1", name="editor", human=True):
        return self.send(name, self.command("cloud_consent", {
            "requestId": request, "provider": provider,
            "payloadDigest": digest, "eventId": event,
        }, human=human))

    def reserve(self, *, request=RID, provider="local_ollama",
                digest=DIGEST, tokens=100, cost=0,
                event="reserve-1", name="editor"):
        return self.send(name, self.command("reserve", {
            "requestId": request, "provider": provider,
            "payloadDigest": digest, "estimatedTokens": tokens,
            "maxCostMicro": cost, "eventId": event,
        }))

    def test_real_password_authenticated_session_and_admin_set_read(self):
        token = self.service.authenticate(
            "owner", "synthetic-owner-password")["token"]
        setcmd = self.command("grant_set", {
            "userId": "editor", "provider": "local_ollama",
            "enabled": True, "cloudEnabled": False,
            "monthlyRequests": 2, "monthlyTokens": 500,
            "monthlyCostMicro": 0, "expectedVersion": 0,
            "eventId": "grant-password",
        })
        result = self.adapter.handle(token, json.dumps(setcmd))
        self.assertEqual(result["result"]["version"], 1)
        self.assertEqual(result["grantScope"], {
            "projectId": "project-one", "userId": "editor",
            "provider": "local_ollama",
        })
        grant = self.send("owner", self.command(
            "grant_get", {"userId": "editor", "provider": "local_ollama"}))
        self.assertEqual(grant["grantScope"], {
            "projectId": "project-one", "userId": "editor",
            "provider": "local_ollama",
        })
        self.assertTrue(grant["result"]["enabled"])
        self.assertFalse(grant["result"]["cloud_enabled"])
        self.assertEqual(grant["result"]["monthly_requests"], 2)
        self.assertEqual(grant["schemaVersion"], 1)
        self.assertIsNone(self.service.server)

    def test_no_grant_or_ai_off_does_not_create_reservation(self):
        self.denies("grant_denied", "editor", self.command("reserve", {
            "requestId": RID, "provider": "local_ollama",
            "payloadDigest": DIGEST, "estimatedTokens": 10,
            "maxCostMicro": 0, "eventId": "attempt-no-grant",
        }))
        self.grant()
        self.service.users["editor"]["aiEnabled"] = False
        self.denies("ai_disabled", "editor", self.command("reserve", {
            "requestId": RID, "provider": "local_ollama",
            "payloadDigest": DIGEST, "estimatedTokens": 10,
            "maxCostMicro": 0, "eventId": "attempt-ai-disabled",
        }))
        self.denies("ai_disabled", "editor", self.command(
            "usage_get", {"provider": "local_ollama"}))
        with closing(sqlite3.connect(self.root / "usage.sqlite")) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM ai_reservations").fetchone()[0], 0)

    def test_local_budget_reservation_durable_without_dispatch(self):
        self.grant(requests=1, tokens=100)
        with patch.object(socket, "socket",
                          side_effect=AssertionError("network forbidden")):
            first = self.reserve(tokens=100)
            self.assertEqual(first["result"]["status"], "reserved")
            self.assertFalse(first["result"]["replayed"])
            usage = self.send("editor", self.command(
                "usage_get", {"provider": "local_ollama"}))
            self.assertEqual(usage["result"]["charged_requests"], 1)
            self.assertEqual(usage["result"]["charged_tokens"], 100)
        reopened = AiUsageStore(self.root / "usage.sqlite")
        reopened_adapter = MadarAiUsageHostAdapter(
            self.service, reopened, org_id="org-a",
            identity_key=self.identity_key, clock=lambda: self.instant)
        self.assertEqual(reopened_adapter.handle(
            self.tokens["editor"], json.dumps(self.command(
                "reservation_get", {"requestId": RID})))["result"]["status"],
            "reserved")
        self.assertEqual(self.send("editor", self.command(
            "reservation_get", {"requestId": RID}))["result"]["status"],
            "reserved")
        self.assertFalse(hasattr(self.adapter, "dispatch"))
        self.assertFalse(hasattr(self.adapter, "mark_dispatched"))

    def test_cloud_default_denied_and_approval_one_use_bound(self):
        self.grant(provider="openai", cloud=False, cost=500)
        self.denies("grant_denied", "editor", self.command("cloud_consent", {
            "requestId": RID, "provider": "openai",
            "payloadDigest": DIGEST, "eventId": "denied-cloud",
        }))
        self.grant(provider="openai", cloud=True, cost=500,
                   version=1, event="enable-cloud")
        self.assertEqual(self.consent()["result"], "recorded")
        self.assertEqual(self.consent()["result"], "recorded_replay")
        one = self.reserve(provider="openai", tokens=90, cost=100)
        self.assertEqual(one["result"]["version"], 1)
        self.assertEqual(one["result"]["status"], "reserved")
        self.denies("request_conflict", "editor", self.command("reserve", {
            "requestId": RID, "provider": "openai",
            "payloadDigest": "d" * 64, "estimatedTokens": 90,
            "maxCostMicro": 100, "eventId": "other-request",
        }))
        self.denies("request_exists", "editor", self.command("cloud_consent", {
            "requestId": RID, "provider": "openai",
            "payloadDigest": DIGEST, "eventId": "other-consent",
        }))
        with closing(sqlite3.connect(self.root / "usage.sqlite")) as db:
            row = db.execute("SELECT state FROM ai_consents WHERE request_id=?",
                             (self.db_request_id(),)).fetchone()
            self.assertEqual(row[0], "consumed")

    def test_cloud_consent_binding_request_provider_digest_and_expiry(self):
        self.grant(provider="gemini", cloud=True, cost=1000)
        self.consent(provider="gemini")
        self.denies("consent_required", "editor", self.command("reserve", {
            "requestId": RID, "provider": "gemini",
            "payloadDigest": "d" * 64, "estimatedTokens": 100,
            "maxCostMicro": 10, "eventId": "wrong-digest",
        }))
        self.denies("consent_required", "editor", self.command("reserve", {
            "requestId": "b" * 32, "provider": "gemini",
            "payloadDigest": DIGEST, "estimatedTokens": 100,
            "maxCostMicro": 10, "eventId": "wrong-request",
        }))
        self.instant = NOW + timedelta(minutes=5)
        self.denies("consent_required", "editor", self.command("reserve", {
            "requestId": RID, "provider": "gemini",
            "payloadDigest": DIGEST, "estimatedTokens": 100,
            "maxCostMicro": 10, "eventId": "expired",
        }))

    def test_revoked_role_project_or_ai_enabled_fails_fresh(self):
        self.grant()
        self.service.users["editor"]["role"] = "viewer"
        self.denies("ai_disabled", "editor", self.command(
            "usage_get", {"provider": "local_ollama"}))
        self.service.users["editor"]["role"] = "editor"
        self.service.users["editor"]["projects"] = ["project-two"]
        self.denies("scope_denied", "editor", self.command(
            "usage_get", {"provider": "local_ollama"}))
        self.service.users["editor"]["projects"] = ["project-one"]
        self.bridge.saved["projects"] = [{"id": "project-two"}]
        self.denies("scope_denied", "editor", self.command(
            "usage_get", {"provider": "local_ollama"}))
        self.bridge.saved["projects"].append({"id": "project-one"})
        self.service.users["editor"]["aiEnabled"] = False
        self.denies("ai_disabled", "editor", self.command("cloud_consent", {
            "requestId": RID, "provider": "openai",
            "payloadDigest": DIGEST, "eventId": "disabled-consent",
        }))

    def test_expired_session_deleted_user_and_bad_token(self):
        with self.assertRaises(AiUsageHostError) as bad:
            self.adapter.handle("bad", json.dumps(self.command(
                "usage_get", {"provider": "local_ollama"})))
        self.assertEqual(bad.exception.code, "authentication_required")
        self.service.sessions[self.tokens["editor"]] = ("editor", time.time() - 1)
        self.denies("authentication_required", "editor", self.command(
            "usage_get", {"provider": "local_ollama"}))
        self.service.sessions[self.tokens["editor"]] = (
            "editor", time.time() + 3600)
        self.service.users.pop("editor")
        self.denies("authentication_required", "editor", self.command(
            "usage_get", {"provider": "local_ollama"}))

    def test_viewer_cannot_change_policy_or_reserve(self):
        self.denies("permission_denied", "viewer", self.command(
            "grant_get", {"userId": "editor", "provider": "openai"}))
        self.denies("permission_denied", "viewer", self.command("grant_set", {
            "userId": "viewer", "provider": "openai", "enabled": True,
            "cloudEnabled": True, "monthlyRequests": 20,
            "monthlyTokens": 1000, "monthlyCostMicro": 100,
            "expectedVersion": 0, "eventId": "viewer-set",
        }))
        self.denies("ai_disabled", "viewer", self.command("reserve", {
            "requestId": RID, "provider": "local_ollama",
            "payloadDigest": DIGEST, "estimatedTokens": 10,
            "maxCostMicro": 0, "eventId": "viewer-reserve",
        }))

    def test_admin_scope_target_is_current_lan_member_only(self):
        self.denies("target_denied", "owner", self.command("grant_set", {
            "userId": "sibling", "provider": "local_ollama",
            "enabled": True, "cloudEnabled": False,
            "monthlyRequests": 10, "monthlyTokens": 1000,
            "monthlyCostMicro": 0, "expectedVersion": 0,
            "eventId": "outside-project",
        }))
        self.denies("target_denied", "owner", self.command(
            "grant_get", {"userId": "viewer", "provider": "openai"}))
        self.denies("target_denied", "owner", self.command(
            "grant_get", {"userId": "not-in-registry", "provider": "openai"}))
        self.grant()
        self.service.users["editor"]["projects"] = []
        self.denies("target_denied", "owner", self.command(
            "grant_get", {"userId": "editor", "provider": "local_ollama"}))
        self.service.users["editor"]["projects"] = ["project-one"]
        self.assertIsNotNone(self.send("owner", self.command(
            "grant_get", {"userId": "editor", "provider": "local_ollama"})
        )["result"])

    def test_admin_grant_cas_replay_after_time_change_and_revocation(self):
        first = self.grant()
        self.assertEqual(first["result"]["version"], 1)
        self.instant = NOW + timedelta(seconds=20)
        self.assertEqual(self.grant()["result"]["version"], 1)
        self.grant(provider="local_ollama", enabled=False, version=1,
                   event="revoke", requests=2, tokens=500)
        self.denies("grant_denied", "editor", self.command("reserve", {
            "requestId": RID, "provider": "local_ollama",
            "payloadDigest": DIGEST, "estimatedTokens": 1,
            "maxCostMicro": 0, "eventId": "after-revoke",
        }))
        self.denies("version_conflict", "owner", self.command("grant_set", {
            "userId": "editor", "provider": "local_ollama",
            "enabled": True, "cloudEnabled": False,
            "monthlyRequests": 2, "monthlyTokens": 500,
            "monthlyCostMicro": 0, "expectedVersion": 1,
            "eventId": "stale-admin",
        }))

    def test_consent_replay_across_adapter_restart_uses_host_event_time(self):
        self.grant(provider="openai", cloud=True, cost=500)
        self.consent()
        later = NOW + timedelta(minutes=2)
        adapter = MadarAiUsageHostAdapter(
            self.service, AiUsageStore(self.root / "usage.sqlite"),
            org_id="org-a", identity_key=self.identity_key,
            clock=lambda: later)
        command = self.command("cloud_consent", {
            "requestId": RID, "provider": "openai",
            "payloadDigest": DIGEST, "eventId": "cloud-consent-1",
        })
        response = adapter.handle(self.tokens["editor"], json.dumps(command))
        self.assertEqual(response["result"], "recorded_replay")
        with closing(sqlite3.connect(self.root / "usage.sqlite")) as db:
            self.assertEqual(db.execute(
                "SELECT expires FROM ai_consents WHERE request_id=?",
                (self.db_request_id(),)).fetchone()[0], "2026-11-09T19:05:00Z")

    def test_event_collision_and_budget_limits(self):
        self.grant(requests=1, tokens=100)
        self.reserve(tokens=100)
        self.denies("event_conflict", "editor", self.command("reserve", {
            "requestId": RID, "provider": "local_ollama",
            "payloadDigest": DIGEST, "estimatedTokens": 99,
            "maxCostMicro": 0, "eventId": "reserve-1",
        }))
        self.denies("budget_exceeded", "editor", self.command("reserve", {
            "requestId": "b" * 32, "provider": "local_ollama",
            "payloadDigest": DIGEST, "estimatedTokens": 1,
            "maxCostMicro": 0, "eventId": "reserve-2",
        }))
        self.assertEqual(self.send("editor", self.command(
            "usage_get", {"provider": "local_ollama"})
        )["result"]["charged_requests"], 1)
        self.instant += timedelta(minutes=1)
        replay = self.reserve(tokens=100)
        self.assertTrue(replay["result"]["replayed"])
        self.assertEqual(replay["result"]["version"], 1)

    def test_consent_revoke_uses_current_ai_enabled_and_valid_session(self):
        self.grant(provider="anthropic", cloud=True, cost=1000)
        self.consent(provider="anthropic")
        self.assertEqual(self.send("editor", self.command("consent_revoke", {
            "requestId": RID, "eventId": "revoke-consent",
        }))["result"], "revoked")
        self.denies("consent_required", "editor", self.command("reserve", {
            "requestId": RID, "provider": "anthropic",
            "payloadDigest": DIGEST, "estimatedTokens": 20,
            "maxCostMicro": 10, "eventId": "reserve-after-revoke",
        }))
        self.service.users["editor"]["aiEnabled"] = False
        self.denies("ai_disabled", "editor", self.command("consent_revoke", {
            "requestId": RID, "eventId": "second-revoke",
        }))

    def test_no_dispatch_actions_can_be_invoked(self):
        self.grant()
        self.reserve()
        for action in ("mark_dispatched", "complete", "cancel", "refund",
                       "generate", "send", "download_model", "api_key",
                       "fallback", "provider_call"):
            with self.subTest(action=action):
                self.denies("unsupported_action", "editor",
                            self.command(action, {
                                "requestId": RID, "eventId": "attempt",
                            }))
        self.assertEqual(self.send("editor", self.command(
            "reservation_get", {"requestId": RID})
        )["result"]["status"], "reserved")

    def test_strict_json_rejects_duplicate_nested_unknown_nan_and_big(self):
        valid = self.command("usage_get", {"provider": "local_ollama"})
        for raw, expected in (
            (b'{"schemaVersion":1,"action":"usage_get","action":"grant_get"}',
             "invalid_json"),
            (b'{"schemaVersion":1,"action":"usage_get",'
             b'"projectId":"project-one","data":{"provider":"openai",'
             b'"provider":"gemini"}}', "invalid_json"),
            (b'{"schemaVersion":1,"action":"usage_get",'
             b'"projectId":"project-one","data":{"provider":NaN}}',
             "invalid_json"),
            (b"\xff", "invalid_json"),
            (b" " * 4097, "invalid_json"),
            (b"[]", "invalid_command"),
            (b"{}", "unsupported_action"),
        ):
            with self.subTest(raw=raw[:20]):
                with self.assertRaises(AiUsageHostError) as caught:
                    self.adapter.handle(self.tokens["editor"], raw)
                self.assertEqual(caught.exception.code, expected)
        for command, expected in (
            ({**valid, "userId": "owner"}, "invalid_command"),
            ({**valid, "role": "admin"}, "invalid_command"),
            ({**valid, "orgId": "org-b"}, "invalid_command"),
            ({**valid, "manualAction": True}, "invalid_command"),
            ({**valid, "data": {"provider": "openai", "amount": 1}},
             "invalid_data"),
            ({**valid, "data": {"provider": "openai", "text": "private"}},
             "invalid_data"),
            ({**valid, "schemaVersion": True}, "invalid_command"),
            ({**valid, "data": {"provider": 1}}, "invalid_provider"),
            ({**valid, "data": {"provider": "local_ollama",
                               "extra": {"apiKey": "never"}}}, "invalid_data"),
        ):
            with self.subTest(command=str(command)[:80]):
                self.denies(expected, "editor", command)

    def test_consent_must_be_explicit_human_action_and_digest_only(self):
        self.grant(provider="openai", cloud=True, cost=100)
        self.denies("manual_action_required", "editor",
                    self.command("cloud_consent", {
                        "requestId": RID, "provider": "openai",
                        "payloadDigest": DIGEST, "eventId": "event-no-human",
                    }, human=1))
        self.denies("invalid_digest", "editor", self.command("cloud_consent", {
            "requestId": RID, "provider": "openai",
            "payloadDigest": "actual client prompt", "eventId": "bad-prompt",
        }))
        self.denies("invalid_data", "editor", self.command("cloud_consent", {
            "requestId": RID, "provider": "openai",
            "payloadDigest": DIGEST, "eventId": "hidden",
            "apiKey": "sk-synthetic-NEVER-SAVED",
        }))

    def test_expiry_and_utc_month_rollover_from_host_clock(self):
        self.grant(requests=1, tokens=100)
        self.instant = datetime(2026, 11, 30, 23, 59, 59,
                                tzinfo=timezone.utc)
        self.reserve(tokens=100)
        self.assertEqual(self.send("editor", self.command("usage_get", {
            "provider": "local_ollama",
        }))["result"]["month_utc"], "2026-11")
        self.instant = datetime(2026, 12, 1, 0, 0, 0,
                                tzinfo=timezone.utc)
        self.assertEqual(self.send("editor", self.command("usage_get", {
            "provider": "local_ollama",
        }))["result"]["charged_requests"], 0)
        self.reserve(request="b" * 32, event="reserve-dec", tokens=100)
        self.assertEqual(self.send("editor", self.command("usage_get", {
            "provider": "local_ollama",
        }))["result"]["month_utc"], "2026-12")

    def test_tenant_isolation_two_hosts_same_sqlite(self):
        self.grant()
        self.reserve()
        otherroot = self.root / "other"
        otherroot.mkdir()
        otherbridge = MemoryBridge()
        other = LanService(otherbridge, otherroot / "users.json",
                           bind="127.0.0.1", port=0)
        other.users = deepcopy(self.accounts)
        other._store_users()
        other.sessions[self.tokens["editor"]] = ("editor", time.time() + 3600)
        other.sessions[self.tokens["owner"]] = ("owner", time.time() + 3600)
        adapter = MadarAiUsageHostAdapter(
            other, self.store, org_id="org-b",
            identity_key=self.identity_key, clock=lambda: NOW)
        self.assertIsNone(adapter.handle(
            self.tokens["owner"],
            json.dumps(self.command("grant_get", {
                "userId": "editor", "provider": "local_ollama",
            })))["result"])
        with self.assertRaises(AiUsageError) as caught:
            adapter.handle(self.tokens["editor"], json.dumps(
                self.command("reservation_get", {"requestId": RID})))
        self.assertEqual(caught.exception.code, "not_found")
        adapter.handle(self.tokens["owner"], json.dumps(
            self.command("grant_set", {
                "userId": "editor", "provider": "local_ollama",
                "enabled": True, "cloudEnabled": False,
                "monthlyRequests": 1, "monthlyTokens": 100,
                "monthlyCostMicro": 0, "expectedVersion": 0,
                "eventId": "set-grant-1",
            })))
        adapter.handle(self.tokens["editor"], json.dumps(self.command(
            "reserve", {
                "requestId": RID, "provider": "local_ollama",
                "payloadDigest": "d" * 64, "estimatedTokens": 25,
                "maxCostMicro": 0, "eventId": "reserve-1",
            })))
        self.assertEqual(self.send("editor", self.command(
            "usage_get", {"provider": "local_ollama"})
        )["result"]["charged_tokens"], 100)
        self.assertEqual(adapter.handle(self.tokens["editor"], json.dumps(
            self.command("usage_get", {"provider": "local_ollama"})
        ))["result"]["charged_tokens"], 25)

    def test_two_simultaneous_reserves_cannot_overbook(self):
        self.grant(requests=1, tokens=100)
        gate = Barrier(2)

        def worker(n):
            command = self.command("reserve", {
                "requestId": f"{n:032x}", "provider": "local_ollama",
                "payloadDigest": DIGEST, "estimatedTokens": 100,
                "maxCostMicro": 0, "eventId": f"reserve-race-{n}",
            })
            gate.wait(timeout=5)
            try:
                return ("allowed", self.send("editor", command)["result"]["version"])
            except AiUsageError as exc:
                return ("denied", exc.code)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, n) for n in (1, 2)]
            outcomes = [f.result(timeout=10) for f in futures]
        self.assertEqual(sorted(outcomes),
                         [("allowed", 1), ("denied", "budget_exceeded")])
        self.assertEqual(self.send("editor", self.command(
            "usage_get", {"provider": "local_ollama"})
        )["result"]["charged_requests"], 1)

    def test_persistent_database_contains_no_lan_identifiers_secret_or_raw_digest(self):
        self.grant(provider="openai", cloud=True, cost=500)
        self.consent()
        self.reserve(provider="openai", tokens=90, cost=100)
        with closing(sqlite3.connect(self.root / "usage.sqlite")) as db:
            saved_ids = db.execute(
                "SELECT org,project,user,request_id,digest FROM ai_reservations"
            ).fetchone()
            self.assertEqual(len(saved_ids[0]), 64)
            self.assertEqual(len(saved_ids[1]), 64)
            self.assertEqual(len(saved_ids[2]), 64)
            self.assertEqual(len(saved_ids[3]), 32)
            self.assertEqual(len(saved_ids[4]), 64)
        raw = (self.root / "usage.sqlite").read_bytes()
        for forbidden in (
            b"org-a", b"project-one", b"owner", b"editor", RID.encode(),
            DIGEST.encode(), self.identity_key,
            b"synthetic-owner-password", b"apiKey", b"promptText",
        ):
            with self.subTest(forbidden=forbidden[:22]):
                self.assertNotIn(forbidden, raw)

    def test_bad_or_rotated_host_identity_secret_cannot_access_old_grants(self):
        with self.assertRaises(AiUsageHostError) as caught:
            MadarAiUsageHostAdapter(
                self.service, self.store, org_id="org-a",
                identity_key=b"not-long-enough",
            )
        self.assertEqual(caught.exception.code, "invalid_identity_key")
        self.grant()
        rotated = MadarAiUsageHostAdapter(
            self.service, self.store, org_id="org-a",
            identity_key=b"a different synthetic private host key 12345",
            clock=lambda: self.instant,
        )
        grant = rotated.handle(self.tokens["owner"], json.dumps(
            self.command("grant_get", {
                "userId": "editor", "provider": "local_ollama",
            })))
        self.assertIsNone(grant["result"])

    def test_old_cloud_consent_dies_when_admin_changes_grant_version(self):
        self.grant(provider="openai", cloud=True, cost=500)
        self.consent()
        self.grant(provider="openai", cloud=True, cost=500,
                   version=1, event="grant-new-version")
        self.denies("consent_required", "editor", self.command("reserve", {
            "requestId": RID, "provider": "openai",
            "payloadDigest": DIGEST, "estimatedTokens": 20,
            "maxCostMicro": 10, "eventId": "obsolete-consent",
        }))
        self.assertEqual(self.send("editor", self.command(
            "usage_get", {"provider": "openai"})
        )["result"]["charged_requests"], 0)

    def test_host_clock_must_be_timezone_aware_and_cannot_be_client_overridden(self):
        self.grant()
        self.instant = datetime(2026, 11, 9, 19, 0)
        self.denies("invalid_clock", "editor", self.command(
            "usage_get", {"provider": "local_ollama"}))
        self.instant = NOW
        self.denies("invalid_command", "editor", {
            **self.command("usage_get", {"provider": "local_ollama"}),
            "atUtc": "2026-12-01T00:00:00Z",
        })
        self.denies("invalid_data", "editor", self.command(
            "usage_get", {"provider": "local_ollama",
                          "atUtc": "2026-12-01T00:00:00Z"}))

    def test_saved_state_corruption_and_missing_grants_are_fail_closed(self):
        self.grant()
        self.bridge.saved["projects"].append({"id": "project-one"})
        self.denies("scope_denied", "editor", self.command(
            "usage_get", {"provider": "local_ollama"}))
        self.bridge.saved["projects"].pop()
        self.service.users["editor"].pop("projects")
        self.denies("scope_denied", "editor", self.command(
            "usage_get", {"provider": "local_ollama"}))
        self.service.users["editor"]["projects"] = [["bad-unhashable"]]
        self.denies("scope_denied", "editor", self.command(
            "usage_get", {"provider": "local_ollama"}))
        self.service.users["editor"]["projects"] = ["project-one"]
        self.service.users["fake"] = ["not-a-user"]
        self.denies("authentication_required", "editor", self.command(
            "usage_get", {"provider": "local_ollama"}))


if __name__ == "__main__":
    unittest.main()
