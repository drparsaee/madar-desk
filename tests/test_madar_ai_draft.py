"""Offline synthetic checks for the opt-in local Ollama task-preview adapter."""

import copy
import hashlib
import json
import socket
import unittest
from unittest.mock import MagicMock, patch

from madar_ai_draft import DraftError, generate_task_draft


SOURCE = "برای سفارش جدید کار چاپ و بسته‌بندی انجام شود؛ تعداد ۵۰ و فی ۱۰۰ نامشخص است."
MODEL_RESULT = {
    "schemaVersion": 1,
    "title": "بررسی سفارش چاپ و بسته‌بندی",
    "checklist": ["بررسی نیازمندی‌های سفارش", "تأیید تعداد و واحد قیمت"],
    "missingFields": ["quantity", "unitPrice", "dueDate"],
}


class FakeResponse:
    def __init__(self, payload, status=200):
        self.status = status
        self.payload = payload
        self.limits = []

    def read(self, size):
        self.limits.append(size)
        return self.payload[:size]


class AdapterTests(unittest.TestCase):
    def invoke(self, *, draft=None, text=SOURCE, envelope=None,
               status=200, **kwargs):
        raw = envelope if envelope is not None else {
            "model": "qwen3:4b",
            "done": True,
            "response": json.dumps(draft if draft is not None else MODEL_RESULT,
                                   ensure_ascii=False),
        }
        wire = (raw if isinstance(raw, bytes) else
                json.dumps(raw, ensure_ascii=False).encode("utf-8"))
        response = FakeResponse(wire, status)
        transport = MagicMock()
        transport.getresponse.return_value = response
        with patch("madar_ai_draft.http.client.HTTPConnection",
                   return_value=transport) as factory:
            result = generate_task_draft(text, opt_in=True, **kwargs)
        return result, factory, transport, response

    def rejects(self, code, **kwargs):
        with self.assertRaises(DraftError) as caught:
            self.invoke(**kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_happy_path_preview_local_only_no_write(self):
        original = copy.deepcopy(MODEL_RESULT)
        result, factory, transport, response = self.invoke()
        self.assertEqual(result["status"], "preview")
        self.assertEqual(result["source"], "local_ollama")
        self.assertEqual(result["model"], "qwen3:4b")
        self.assertTrue(result["requiresHumanReview"])
        self.assertEqual(result["draft"], original)
        self.assertEqual(result["inputSha256"],
                         hashlib.sha256(SOURCE.encode("utf-8")).hexdigest())
        factory.assert_called_once_with("127.0.0.1", 11434, timeout=10.0)
        args, kwargs = transport.request.call_args
        self.assertEqual(args[:2], ("POST", "/api/generate"))
        payload = json.loads(kwargs["body"])
        self.assertEqual(payload["model"], "qwen3:4b")
        self.assertEqual(payload["stream"], False)
        self.assertIs(payload["think"], False)
        self.assertEqual(payload["format"], "json")
        self.assertIn(SOURCE, payload["prompt"])
        self.assertNotIn("download", payload)
        self.assertEqual(response.limits, [24_577])
        transport.close.assert_called_once()
        self.assertEqual(original, MODEL_RESULT)
        self.assertEqual(set(result["draft"]),
                         {"schemaVersion", "title", "checklist", "missingFields"})

    def test_opt_in_required_at_adapter_boundary_without_network(self):
        with patch("madar_ai_draft.http.client.HTTPConnection") as transport:
            for choice in (False, None, 1, "true"):
                with self.subTest(choice=choice):
                    with self.assertRaises(DraftError) as caught:
                        generate_task_draft(SOURCE, opt_in=choice)
                    self.assertEqual(caught.exception.code, "opt_in_required")
            transport.assert_not_called()

    def test_fixed_installed_model_and_timeout(self):
        with patch("madar_ai_draft.http.client.HTTPConnection") as transport:
            for model in ("qwen2.5:3b", "qwen3:8b", "http://evil", "", None):
                with self.subTest(model=model):
                    with self.assertRaises(DraftError) as caught:
                        generate_task_draft(SOURCE, opt_in=True, model=model)
                    self.assertEqual(caught.exception.code, "invalid_model")
            for timeout in (0, 21, True, "4"):
                with self.subTest(timeout=timeout):
                    with self.assertRaises(DraftError) as caught:
                        generate_task_draft(SOURCE, opt_in=True,
                                            timeout_seconds=timeout)
                    self.assertEqual(caught.exception.code, "invalid_timeout")
            transport.assert_not_called()

    def test_invalid_or_oversized_input_does_not_contact_model(self):
        with patch("madar_ai_draft.http.client.HTTPConnection") as transport:
            for text in ("", "   ", "\u202eunsafe", "x" * 4_001, 22, "\ud800"):
                with self.subTest(text=repr(text)[:40]):
                    with self.assertRaises(DraftError):
                        generate_task_draft(text, opt_in=True)
            with self.assertRaises(DraftError) as caught:
                generate_task_draft("🧪" * 2_200, opt_in=True)
            self.assertEqual(caught.exception.code, "input_too_large")
            transport.assert_not_called()

    def test_malformed_json_duplicate_keys_and_unknown_fields(self):
        for body in (b"bad json", b'{"schemaVersion":1,"schemaVersion":1}',
                     b'{"schemaVersion":NaN}',
                     b'["not an object"]'):
            with self.subTest(body=body):
                self.rejects("invalid_model_output", envelope={
                    "done": True, "response": body.decode("utf-8")})
        wrong = {**MODEL_RESULT, "amountRial": 1234}
        self.rejects("invalid_model_output", draft=wrong)
        wrong = {**MODEL_RESULT, "schemaVersion": True}
        self.rejects("invalid_model_output", draft=wrong)
        wrong = {**MODEL_RESULT, "title": ["not a title"]}
        self.rejects("invalid_model_output", draft=wrong)
        wrong = {**MODEL_RESULT, "missingFields": ["bankAccount"]}
        self.rejects("invalid_model_output", draft=wrong)
        wrong = {**MODEL_RESULT, "checklist": ["item"] * 9}
        self.rejects("invalid_model_output", draft=wrong)
        wrong = {**MODEL_RESULT, "checklist": ["duplicate", "duplicate"]}
        self.rejects("invalid_model_output", draft=wrong)

    def test_rejects_contact_leaks_and_control_chars(self):
        self.rejects("sensitive_model_output", draft={
            **MODEL_RESULT, "title": "تماس با 09123456789"})
        self.rejects("sensitive_model_output", draft={
            **MODEL_RESULT, "checklist": ["ارسال به test@example.com"]})
        self.rejects("sensitive_model_output", draft={
            **MODEL_RESULT, "checklist": ["بازکردن https://example.com"]})
        self.rejects("sensitive_model_output", draft={
            **MODEL_RESULT, "checklist": ["قیمت ۱۰۰۰ ریال"]})
        self.rejects("invalid_model_output", draft={
            **MODEL_RESULT, "title": "عنوان\u202eفریب"})

    def test_missing_fields_remain_review_prompts_never_values(self):
        result, *_ = self.invoke()
        self.assertEqual(result["draft"]["missingFields"],
                         ["quantity", "unitPrice", "dueDate"])
        self.assertNotIn("fields", result["draft"])
        self.assertNotIn("unitPriceRial", result["draft"])
        self.assertNotIn("customer", result["draft"])
        self.assertNotIn("supplier", result["draft"])

    def test_fail_closed_on_incomplete_envelope_and_status(self):
        self.rejects("invalid_model_output",
                     envelope={"done": False, "response": "{}"})
        self.rejects("invalid_model_output",
                     envelope={"done": True, "response": []})
        self.rejects("model_unavailable", status=404)
        self.rejects("response_too_large",
                     envelope=b"x" * 24_578)
        self.rejects("response_too_large", envelope={
            "done": True, "response": "x" * 12_500})

    def test_connection_failure_timeout_closes_without_retry(self):
        with patch("madar_ai_draft.http.client.HTTPConnection") as factory:
            client = factory.return_value
            client.request.side_effect = socket.timeout("timeout")
            with self.assertRaises(DraftError) as caught:
                generate_task_draft(SOURCE, opt_in=True)
            self.assertEqual(caught.exception.code, "model_unavailable")
            client.close.assert_called_once()
            self.assertEqual(factory.call_count, 1)
            self.assertEqual(client.request.call_count, 1)


if __name__ == "__main__":
    unittest.main()
