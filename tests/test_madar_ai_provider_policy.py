"""Pure synthetic provider-policy tests: no network, keys, state or finance."""

from copy import deepcopy
import hashlib
import json
import socket
import unittest
from unittest.mock import patch

from madar_ai_provider_policy import (
    PolicyValidationError,
    evaluate_ai_request,
    validate_provider_configuration,
)


REQUEST_ID = "a" * 32
TEXT = "برای یک سفارش چاپ، لطفا فهرست کارهای آماده‌سازی را پیشنهاد بده."
PROVIDERS = ("local_ollama", "openai", "gemini", "anthropic")
TEXT_SHA = hashlib.sha256(TEXT.encode("utf-8")).hexdigest()
UNSET = object()


class ProviderPolicyTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "schemaVersion": 1,
            "cloudEnabled": False,
            "enabledProviders": ["local_ollama"],
            "users": {
                "editor-1": {"aiEnabled": True,
                             "allowedProviders": ["local_ollama"]}
            },
            "projects": {
                "project-1": {"allowedProviders": ["local_ollama"]}
            },
        }
        self.request = {
            "schemaVersion": 1, "requestId": REQUEST_ID,
            "projectId": "project-1", "provider": "local_ollama",
            "purpose": "task_draft_preview",
            "contentSource": "user_selected_text", "text": TEXT,
        }
        self.session = {
            "authenticated": True, "userId": "editor-1",
            "role": "editor", "projectGrants": ["project-1"],
        }
        self.runtime = {
            "selectedTextVerified": True,
            "networkAvailable": False,
            "ephemeralCredentialAvailable": False,
            "cloudConsentVerified": False,
            "spentCloudRequestIds": [],
        }

    def run_policy(self, *, config=UNSET, request=UNSET, session=UNSET,
                   runtime=UNSET, consent=None):
        return evaluate_ai_request(
            self.config if config is UNSET else config,
            self.request if request is UNSET else request,
            session=self.session if session is UNSET else session,
            runtime=self.runtime if runtime is UNSET else runtime,
            cloud_consent=consent,
        )

    def assert_denied(self, reason, **changes):
        decision = self.run_policy(**changes)
        self.assertFalse(decision["allowed"], decision)
        self.assertEqual(decision["reason"], reason, decision)
        self.assertIsNone(decision["textSha256"])
        self.assertTrue(decision["requiresHumanReview"])
        self.assertNotIn("text", decision)
        self.assertNotIn("credential", decision)
        return decision

    def cloud(self, provider="openai"):
        config = deepcopy(self.config)
        config["cloudEnabled"] = True
        config["enabledProviders"] = list(PROVIDERS)
        config["users"]["editor-1"]["allowedProviders"] = list(PROVIDERS)
        config["projects"]["project-1"]["allowedProviders"] = list(PROVIDERS)
        request = {**self.request, "provider": provider}
        runtime = {
            **self.runtime, "networkAvailable": True,
            "ephemeralCredentialAvailable": True,
            "cloudConsentVerified": True,
        }
        consent = {
            "approved": True, "userId": "editor-1",
            "requestId": REQUEST_ID, "provider": provider,
            "textSha256": TEXT_SHA,
        }
        return dict(config=config, request=request, runtime=runtime,
                    consent=consent)

    def test_local_allowed_offline_without_credential_or_cloud_consent(self):
        with patch.object(socket, "socket", side_effect=AssertionError("network forbidden")):
            decision = self.run_policy()
        self.assertEqual(decision, {
            "policyVersion": 1, "allowed": True, "reason": "allowed_local",
            "provider": "local_ollama", "textSha256": TEXT_SHA,
            "requiresHumanReview": True,
        })

    def test_no_provider_fallback_when_local_disabled_or_cloud_offline(self):
        config = deepcopy(self.config)
        config["enabledProviders"] = ["openai", "gemini"]
        self.assert_denied("provider_disabled", config=config)
        cloud = self.cloud()
        cloud["runtime"]["networkAvailable"] = False
        self.assert_denied("offline", **cloud)

    def test_all_supported_cloud_providers_require_binding_and_explicit_enable(self):
        for provider in ("openai", "gemini", "anthropic"):
            with self.subTest(provider=provider):
                kw = self.cloud(provider)
                result = self.run_policy(**kw)
                self.assertEqual(result["reason"], "allowed_cloud")
                self.assertTrue(result["allowed"])
                self.assertEqual(result["provider"], provider)
                self.assertEqual(result["textSha256"], TEXT_SHA)
                self.assertNotIn("text", result)

                kw["config"]["cloudEnabled"] = False
                self.assert_denied("cloud_disabled", **kw)

    def test_default_cloud_denied_even_if_globally_allowed(self):
        kw = self.cloud()
        kw["config"]["cloudEnabled"] = False
        self.assert_denied("cloud_disabled", **kw)
        kw["config"]["cloudEnabled"] = True
        kw["config"]["enabledProviders"].remove("openai")
        self.assert_denied("provider_disabled", **kw)

    def test_identity_and_role_cannot_be_bypassed(self):
        for change, reason in (
            ({"authenticated": False}, "unauthenticated"),
            ({"role": "viewer"}, "role_denied"),
            ({"userId": "stranger"}, "user_denied"),
            ({"projectGrants": []}, "project_denied"),
            ({"projectGrants": ["project-other"]}, "project_denied"),
        ):
            with self.subTest(change=change):
                self.assert_denied(reason, session={**self.session, **change})
        self.assertTrue(self.run_policy(
            session={**self.session, "role": "admin"})["allowed"])

    def test_user_and_project_provider_grants_are_independent(self):
        kw = self.cloud()
        kw["config"]["users"]["editor-1"]["allowedProviders"].remove("openai")
        self.assert_denied("user_provider_denied", **kw)
        kw = self.cloud()
        kw["config"]["projects"]["project-1"]["allowedProviders"].remove("openai")
        self.assert_denied("project_provider_denied", **kw)
        kw = self.cloud()
        kw["config"]["users"]["editor-1"]["aiEnabled"] = False
        self.assert_denied("user_denied", **kw)
        kw = self.cloud()
        kw["config"]["projects"] = {}
        self.assert_denied("project_denied", **kw)

    def test_verification_of_exact_user_selected_text_is_required(self):
        self.assert_denied("selection_not_verified", runtime={
            **self.runtime, "selectedTextVerified": False,
        })
        for source in ("task_object", "full_workspace", "financial_records",
                       "", None):
            with self.subTest(source=source):
                self.assert_denied("privacy_scope_denied", request={
                    **self.request, "contentSource": source,
                })

    def test_request_never_accepts_task_or_finance_context_fields(self):
        for field, value in (
            ("task", {"id": "secret-task"}),
            ("finance", [{"invoice": "synthetic"}]),
            ("attachments", ["sample.pdf"]),
            ("context", "other projects"),
            ("apiKey", "placeholder-only"),
            ("fallbackProviders", ["gemini"]),
            ("selectedText", TEXT),
            ("userId", "admin"),
        ):
            with self.subTest(field=field):
                self.assert_denied("invalid_request",
                                   request={**self.request, field: value})

    def test_sensitive_text_or_complete_task_json_is_denied(self):
        for text in (
            '{"id":"abc","title":"draft"}',
            '[{"task":"hidden"}]',
            "حساب بانکی مشتری",
            "مبلغ ۱۰۰۰ تومان",
            "دریافت شماره شبا",
            "invoice number",
            "API_KEY=fake_value",
        ):
            with self.subTest(text=text):
                self.assert_denied("privacy_scope_denied", request={
                    **self.request, "text": text,
                })

    def test_empty_oversized_and_dangerous_texts(self):
        for text in ("", "  ", "x" * 4_001, "🐳" * 2_200,
                     "title\u202eprivate", "\x00", "\ud800", 7):
            with self.subTest(text=repr(text)[:50]):
                self.assert_denied("invalid_text", request={
                    **self.request, "text": text,
                })

    def test_missing_cloud_consent_and_unverified_consent_denied(self):
        kw = self.cloud()
        kw["consent"] = None
        self.assert_denied("invalid_cloud_consent", **kw)
        kw = self.cloud()
        kw["runtime"]["cloudConsentVerified"] = False
        self.assert_denied("cloud_consent_not_verified", **kw)
        kw = self.cloud()
        kw["consent"]["approved"] = False
        self.assert_denied("invalid_cloud_consent", **kw)

    def test_cloud_consent_is_bound_to_user_request_provider_and_text(self):
        for field, wrong in (
            ("userId", "admin-else"),
            ("requestId", "b" * 32),
            ("provider", "gemini"),
            ("textSha256", "0" * 64),
            ("approved", 1),
        ):
            with self.subTest(field=field):
                kw = self.cloud()
                kw["consent"][field] = wrong
                self.assert_denied("invalid_cloud_consent", **kw)
        kw = self.cloud()
        kw["request"]["text"] = TEXT + " بررسی شود."
        self.assert_denied("invalid_cloud_consent", **kw)
        kw = self.cloud()
        kw["consent"]["sessionAllowed"] = True
        self.assert_denied("invalid_cloud_consent", **kw)

    def test_repeat_cloud_request_id_denied_by_host_supplied_spent_ids(self):
        kw = self.cloud()
        kw["runtime"]["spentCloudRequestIds"] = [REQUEST_ID]
        self.assert_denied("cloud_consent_reused", **kw)
        kw = self.cloud()
        kw["runtime"]["spentCloudRequestIds"] = ["c" * 32]
        self.assertTrue(self.run_policy(**kw)["allowed"])

    def test_cloud_requires_network_and_ephemeral_key_each_time(self):
        kw = self.cloud()
        kw["runtime"]["networkAvailable"] = False
        self.assert_denied("offline", **kw)
        kw = self.cloud()
        kw["runtime"]["ephemeralCredentialAvailable"] = False
        self.assert_denied("credential_unavailable", **kw)
        kw = self.cloud()
        kw["runtime"]["ephemeralCredentialAvailable"] = "true"
        self.assert_denied("invalid_runtime", **kw)
        kw = self.cloud()
        kw["runtime"]["apiKey"] = "never-persist"
        self.assert_denied("invalid_runtime", **kw)

    def test_local_rejects_spurious_cloud_consent(self):
        kw = self.cloud()
        self.assert_denied("unexpected_cloud_consent", consent=kw["consent"])

    def test_configuration_validation_is_strict_and_copies_policy(self):
        copied = validate_provider_configuration(self.config)
        self.assertEqual(copied, self.config)
        copied["users"]["editor-1"]["aiEnabled"] = False
        self.assertTrue(self.config["users"]["editor-1"]["aiEnabled"])
        for wrong in (
            {**self.config, "apiKey": "placeholder"},
            {**self.config, "schemaVersion": True},
            {**self.config, "cloudEnabled": "false"},
            {**self.config, "users": {"u": {"aiEnabled": 1,
                                        "allowedProviders": ["openai"]}}},
            {**self.config, "enabledProviders": ["local_ollama",
                                                "local_ollama"]},
            {**self.config, "enabledProviders": ["unapproved"]},
            {**self.config, "users": {"invalid user": {
                "aiEnabled": True, "allowedProviders": ["local_ollama"]}}},
            {**self.config, "projects": {"project-1": {
                "allowedProviders": ["local_ollama"], "secret": "none"}}},
        ):
            with self.subTest(wrong=repr(wrong)[:100]):
                with self.assertRaises(PolicyValidationError):
                    validate_provider_configuration(wrong)
                self.assert_denied("invalid_configuration", config=wrong)

    def test_incomplete_or_malformed_inputs_are_fail_closed(self):
        self.assert_denied("invalid_configuration", config={})
        self.assert_denied("invalid_configuration", config=None)
        self.assert_denied("invalid_request", request={})
        self.assert_denied("invalid_request", request={
            **self.request, "provider": "other",
        })
        self.assert_denied("invalid_request", request={
            **self.request, "requestId": "not-a-nonce",
        })
        self.assert_denied("invalid_request", request={
            **self.request, "schemaVersion": "1",
        })
        self.assert_denied("invalid_session", session={
            **self.session, "role": "administrator",
        })
        self.assert_denied("invalid_session", session={
            **self.session, "projectGrants": ["project-1", "project-1"],
        })
        self.assert_denied("invalid_runtime", runtime={
            **self.runtime, "spentCloudRequestIds": ["bad"],
        })
        self.assert_denied("invalid_runtime", runtime={
            **self.runtime, "spentCloudRequestIds": [REQUEST_ID, REQUEST_ID],
        })
        self.assert_denied("invalid_runtime", runtime={})

    def test_zero_side_effects_no_raw_text_or_key_in_decisions(self):
        kw = self.cloud()
        original = deepcopy(kw)
        with patch.object(socket, "socket", side_effect=AssertionError("network forbidden")), \
             patch("builtins.open", side_effect=AssertionError("disk forbidden")):
            first = self.run_policy(**kw)
            second = self.run_policy(**kw)
        self.assertEqual(first, second)
        self.assertEqual(kw, original)
        decision_json = json.dumps(first)
        self.assertNotIn(TEXT, decision_json)
        self.assertNotIn("ephemeralCredential", decision_json)
        self.assertNotIn("editor-1", decision_json)
        self.assertNotIn("project-1", decision_json)
        self.assertEqual(first["textSha256"], TEXT_SHA)


if __name__ == "__main__":
    unittest.main()
