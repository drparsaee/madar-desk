"""Madar MCP: real stdio JSON-RPC and pinned localhost HTTPS acceptance tests."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

import native_app
from integration_api_v1 import IntegrationResponse
from lan import LanService, certificate_fingerprint
from mcp_stdio_v1 import MCPServer, PinnedIntegrationClient, serve, MAX_FRAME

try:
    from test_lan_tls import _CERT, _KEY  # Public disposable test-only certificate.
except ModuleNotFoundError:
    from tests.test_lan_tls import _CERT, _KEY


def call(identifier, method, params=None):
    item = {"jsonrpc": "2.0", "id": identifier, "method": method}
    if params is not None:
        item["params"] = params
    return item


def handshake():
    return [call(1, "initialize", {"protocolVersion": "2025-11-25",
                                   "clientInfo": {"name": "unit-test", "version": "1"},
                                   "capabilities": {}}),
            {"jsonrpc": "2.0", "method": "notifications/initialized"}]


class MCPStdioV1Tests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="madar-mcp-stdio-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        env = patch.dict(os.environ, {"APPDATA": str(self.root / "appdata"),
                                    "LOCALAPPDATA": str(self.root / "localappdata")})
        env.start()
        self.addCleanup(env.stop)
        (self.root / "store").mkdir(parents=True)
        with patch.object(native_app, "datadir", return_value=self.root / "store"):
            self.bridge = native_app.Bridge()
            self.bridge.saveState(native_app.initial_state())
        self.cert, self.pemkey = self.root / "test.crt", self.root / "test.key"
        self.cert.write_text(_CERT, encoding="ascii")
        self.pemkey.write_text(_KEY, encoding="ascii")
        self.service = LanService(self.bridge, self.root / "users.json",
                                  bind="127.0.0.1", port=0,
                                  certfile=self.cert, keyfile=self.pemkey)
        self.service.setup_owner("owner", "test-password-for-mcp")
        self.service.start()
        self.addCleanup(self.service.stop)
        self.bridge.lan = self.service
        self.bridge.connection = {"mode": "server"}
        self.owner_token = self.service.authenticate("owner", "test-password-for-mcp")["token"]
        self.service.upsert_user(self.owner_token, {"username": "viewer", "password": "mcp-viewer-password",
                                                     "role": "viewer", "projects": ["p-sample"]})
        self.key = self.bridge.integrationIssueKey("viewer", ["read"],
            lifetime_seconds=600, adminCredentials={
                "username": "owner", "password": "test-password-for-mcp"})["key"]
        self.pin = certificate_fingerprint(self.cert)
        self.url = f"https://127.0.0.1:{self.service.port}"

    def client(self, key=None, pin=None):
        return PinnedIntegrationClient(self.url, self.pin if pin is None else pin,
                                       self.key if key is None else key)

    def subprocess(self, frames, *, pin=None, key=None):
        active_key = self.key if key is None else key
        environment = {**os.environ, "MADAR_MCP_URL": self.url,
                       "MADAR_MCP_CERT_SHA256": self.pin if pin is None else pin,
                       "MADAR_MCP_INTEGRATION_KEY": active_key}
        message = b"".join(json.dumps(item, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"
                           if not isinstance(item, bytes) else item for item in frames)
        process = subprocess.run([sys.executable, "-u", str(Path(__file__).resolve().parents[1] / "mcp_stdio_v1.py")],
                                 input=message, capture_output=True, timeout=16, env=environment,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        responses = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertNotIn(active_key.encode(), process.stdout + process.stderr)
        return process, responses

    def test_real_subprocess_legacy_handshake_three_tools_and_https_read(self):
        process, responses = self.subprocess(handshake() + [
            call(2, "tools/list"), call(3, "tools/call", {"name": "madar_list_projects", "arguments": {}}),
            call(4, "tools/call", {"name": "madar_list_cards",
                                          "arguments": {"projectId": "p-sample", "limit": 2}})])
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual([response["id"] for response in responses], [1, 2, 3, 4])
        self.assertEqual(responses[0]["result"]["protocolVersion"], "2025-11-25")
        names = [tool["name"] for tool in responses[1]["result"]["tools"]]
        self.assertEqual(names, ["madar_list_projects", "madar_list_cards", "madar_get_card"])
        self.assertTrue(all(tool["annotations"]["readOnlyHint"] for tool in responses[1]["result"]["tools"]))
        projects = json.loads(responses[2]["result"]["content"][0]["text"])["projects"]
        self.assertEqual([p["id"] for p in projects], ["p-sample"])
        listing = json.loads(responses[3]["result"]["content"][0]["text"])
        self.assertTrue(listing["cards"])
        self.assertLessEqual(len(listing["cards"]), 2)
        for card in listing["cards"]:
            self.assertLessEqual(set(card), {"id", "projectId", "title", "status", "priority", "dueDate"})
        self.assertNotIn("cost", json.dumps(listing))

    def test_get_card_via_real_tls_and_no_finance_fields(self):
        card = next(task for task in self.bridge.getState()["tasks"] if task["projectId"] == "p-sample")
        process, responses = self.subprocess(handshake() + [
            call(2, "tools/call", {"name": "madar_get_card", "arguments": {"cardId": card["id"]}}),
            call(3, "tools/call", {"name": "madar_get_card", "arguments": {"cardId": "not-visible"}})])
        self.assertEqual(process.returncode, 0)
        self.assertFalse(responses[1]["result"]["isError"])
        payload = json.loads(responses[1]["result"]["content"][0]["text"])["card"]
        self.assertEqual(payload["id"], card["id"])
        self.assertNotIn("checklist", payload)
        self.assertNotIn("cost", payload)
        self.assertTrue(responses[2]["result"]["isError"])
        self.assertEqual(responses[2]["result"]["content"][0]["text"], "not_found")

    def test_wrong_pin_is_checked_before_sending_http_credentials(self):
        router = self.service.integration_router
        with patch.object(router, "handle", wraps=router.handle) as observed:
            process, responses = self.subprocess(handshake() + [call(
                2, "tools/call", {"name": "madar_list_cards", "arguments": {}})], pin="0" * 64)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(observed.call_count, 0)
        self.assertEqual(responses[1]["result"]["content"][0]["text"], "certificate_mismatch")
        self.assertTrue(responses[1]["result"]["isError"])

    def test_revoked_key_cannot_read_and_does_not_echo_secret(self):
        issued = self.bridge.integrationIssueKey("viewer", ["read"],
            adminCredentials={"username":"owner","password":"test-password-for-mcp"})
        self.assertEqual(self.bridge.integrationRevokeKey(issued["keyId"],
            {"username":"owner","password":"test-password-for-mcp"}), {"revoked": True})
        process, responses = self.subprocess(handshake() + [call(
            2, "tools/call", {"name": "madar_list_projects", "arguments": {}})], key=issued["key"])
        self.assertEqual(process.returncode, 0)
        self.assertEqual(responses[1]["result"]["content"][0]["text"], "authentication_required")

    def test_https_response_byte_limit_is_applied_before_json_decoding(self):
        router = self.service.integration_router
        over_limit = (b'{"version":1,"projects":[{"name":"' + b'A' * 263000 + b'"}]}')
        def large_response(*_args, **_kwargs):
            return IntegrationResponse(200, {"Content-Type": "application/json"}, over_limit)
        with patch.object(router, "handle", side_effect=large_response) as observed:
            process, results = self.subprocess(handshake() + [call(
                2, "tools/call", {"name": "madar_list_projects", "arguments": {}})])
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(observed.call_count, 1)
        self.assertEqual(results[1]["result"]["content"][0]["text"], "response_too_large")
        self.assertLess(len(process.stdout), 3000)

    def test_untrusted_backend_fields_are_stripped_again_and_rate_limit_enforced(self):
        fake = Mock()
        def payload(path):
            if path.endswith("/projects"):
                return {"version": 1, "projects": [{"id": "p1", "name": "example",
                                                      "finance": 999, "passwordHash": "private"}]}
            return {"version": 1, "revision": "a" * 64, "hasMore": False,
                    "cards": [{"id": "c1", "title": "visible", "cost": 999,
                               "checklist": [{"cost": 111}], "fileLinks": ["private"]}]}
        fake.get.side_effect = payload
        server = MCPServer(fake)
        server.dispatch(handshake()[0]); server.dispatch(handshake()[1])
        projects = server.dispatch(call(2, "tools/call", {"name": "madar_list_projects"}))
        cards = server.dispatch(call(3, "tools/call", {"name": "madar_list_cards"}))
        self.assertEqual(json.loads(projects["result"]["content"][0]["text"]),
                         {"projects": [{"id": "p1", "name": "example"}]})
        stripped = json.loads(cards["result"]["content"][0]["text"])["cards"][0]
        self.assertEqual(stripped, {"id": "c1", "title": "visible"})
        for identifier in range(4, 63):
            result = server.dispatch(call(identifier, "tools/call", {"name": "madar_list_projects"}))
        self.assertTrue(result["result"]["isError"])
        self.assertEqual(result["result"]["content"][0]["text"], "rate_limited")
        self.assertEqual(fake.get.call_count, 60)

    def test_schema_and_method_fails_closed_without_any_http_calls(self):
        server = MCPServer(self.client())
        self.assertEqual(server.dispatch(call(1, "tools/list"))["error"]["code"], -32000)
        server.dispatch(handshake()[0]); server.dispatch(handshake()[1])
        router = self.service.integration_router
        bad_calls = [
            call(2, "tools/call", {"name": "madar_list_cards", "arguments": {"limit": True}}),
            call(3, "tools/call", {"name": "madar_list_cards", "arguments": {"limit": 201}}),
            call(4, "tools/call", {"name": "madar_get_card", "arguments": {"cardId": "../etc/passwd"}}),
            call(5, "tools/call", {"name": "madar_get_card", "arguments": {"cardId": "a?x=y"}}),
            call(6, "tools/call", {"name": "madar_list_cards", "arguments": {"url": "https://evil.test"}}),
            call(7, "tools/call", {"name": "madar_read_file", "arguments": {"path": "test"}}),
            call(8, "tools/call", {"name": "madar_write_card", "arguments": {"cardId": "x"}}),
            call(9, "resources/read", {"uri": "file:///C:/windows"}),
            call(10, "tools/list", {"cursor": "any"}),
            call(11, "tools/call", {"name": "madar_list_projects", "arguments": {"finance": True}}),
        ]
        with patch.object(router, "handle", wraps=router.handle) as observed:
            for sample in bad_calls:
                with self.subTest(sample=sample["id"]):
                    outcome = server.dispatch(sample)
                    self.assertIn(outcome["error"]["code"], (-32601, -32602))
            self.assertEqual(observed.call_count, 0)

    def test_malformed_duplicate_json_and_oversized_framing(self):
        server = MCPServer(self.client())
        bad = b'{"jsonrpc":"2.0","jsonrpc":"2.0","id":2,"method":"tools/list"}\n'
        input_stream = io.BytesIO(bad + b'{invalid\n' +
                                  json.dumps(handshake()[0]).encode() + b"\n" +
                                  json.dumps(handshake()[1]).encode() + b"\n" +
                                  json.dumps(call(3, "tools/list")).encode() + b"\n")
        output_stream = io.BytesIO()
        serve(server, input_stream, output_stream)
        outputs = [json.loads(line) for line in output_stream.getvalue().splitlines()]
        self.assertEqual([row.get("id") for row in outputs], [None, None, 1, 3])
        self.assertEqual([row["error"]["code"] for row in outputs[:2]], [-32700, -32700])
        too_large = io.BytesIO(b"X" * (MAX_FRAME + 1) + b"\n" + json.dumps(call(9, "tools/list")).encode() + b"\n")
        out = io.BytesIO()
        serve(MCPServer(self.client()), too_large, out)
        self.assertEqual(len(out.getvalue().splitlines()), 1)
        self.assertEqual(json.loads(out.getvalue())["error"]["code"], -32700)
        deep = b'[' * 1500 + b'0' + b']' * 1500 + b'\n'
        out = io.BytesIO()
        serve(MCPServer(self.client()), io.BytesIO(deep), out)
        # Parser may accept nesting, in which case its non-object top level is
        # an invalid request; both outcomes fail closed without a crash.
        self.assertIn(json.loads(out.getvalue())["error"]["code"], (-32600, -32700))

    def test_reject_untrusted_endpoints_and_missing_config(self):
        for uri in ("http://127.0.0.1:22", "https://example.com:443", "https://localhost:443",
                    "https://127.0.0.1:443/finance", "https://user:secret@127.0.0.1:443",
                    "https://127.0.0.1:443/?url=file:///tmp", "https://127.0.0.1"):
            with self.subTest(uri=uri), self.assertRaises(ValueError):
                PinnedIntegrationClient(uri, self.pin, self.key)
        environment = {**os.environ, "MADAR_MCP_URL": self.url,
                       "MADAR_MCP_CERT_SHA256": self.pin}
        environment.pop("MADAR_MCP_INTEGRATION_KEY", None)
        process = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "mcp_stdio_v1.py")],
                                 input=b"", capture_output=True, timeout=8, env=environment)
        self.assertEqual(process.returncode, 2)
        self.assertEqual(process.stdout, b"")
        self.assertNotIn(self.url.encode(), process.stderr)


if __name__ == "__main__":
    unittest.main()
