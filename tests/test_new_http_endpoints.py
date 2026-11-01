import base64
import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

import native_app
from tests.legacy_sample_fixture import seed_legacy_example_state
from lan import LanService


class NewHttpEndpointsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.mock = patch.object(native_app, "datadir", return_value=self.root)
        self.mock.start()
        self.bridge = seed_legacy_example_state(native_app.Bridge())
        self.server = LanService(self.bridge, self.root / "accounts.json", "127.0.0.1", 0)
        self.server.setup_owner("admin", "secure-admin-password")
        self.port = self.server.start()
        self.base = "http://127.0.0.1:" + str(self.port)
        self.owner = self.request("/api/login", {"username": "admin", "password": "secure-admin-password"})["token"]
        self.request("/api/user", {"username": "reader", "role": "viewer", "password": "secure-reader-password",
                                   "projects": ["p-sample"]}, self.owner)
        self.viewer = self.request("/api/login", {"username": "reader", "password": "secure-reader-password"})["token"]

    def tearDown(self):
        self.server.stop()
        self.mock.stop()
        self.temp.cleanup()

    def request(self, endpoint, data=None, token=None):
        kwargs = {}
        if data is not None:
            kwargs["data"] = json.dumps(data).encode("utf8")
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        req = Request(self.base + endpoint, headers=headers, **kwargs)
        with urlopen(req, timeout=8) as response:
            return json.loads(response.read())

    def test_http_binary_acl_and_download(self):
        raw = base64.b64encode("hello Madar".encode("utf8")).decode("ascii")
        item = self.request("/api/attachments", {"kind":"upload", "cardId":"example-2",
                "filename":"test.txt","contentBase64":raw,"requestId":"http-upload"},self.owner)["result"]
        public = self.request("/api/attachments?kind=list&cardId=example-2",token=self.viewer)["result"]
        self.assertEqual(len(public), 1)
        self.assertEqual(public[0]["id"], item["id"])
        body = self.request("/api/attachments?kind=read&attachmentId="+item["id"],token=self.viewer)["result"]
        self.assertEqual(body["contentBase64"], raw)
        with self.assertRaises(HTTPError) as error:
            self.request("/api/attachments", {"kind":"delete", "attachmentId":item["id"],
                                              "requestId":"viewer-delete"},self.viewer)
        self.assertEqual(error.exception.code, 403)
        with self.assertRaises(HTTPError) as error:
            self.request("/api/attachments?kind=read&attachmentId="+item["id"])
        self.assertEqual(error.exception.code, 403)

    def test_http_finance_and_rule_endpoints_have_admin_gates(self):
        self.assertEqual(self.request("/api/finance?projectId=p-sample",token=self.owner)["invoices"], [])
        with self.assertRaises(HTTPError) as error:
            self.request("/api/finance?projectId=p-sample",token=self.viewer)
        self.assertEqual(error.exception.code, 403)
        command = {"type":"rule.upsert","eventId":"http-rule",
                   "rule":{"id":"newrule","projectId":"p-sample","trigger":"card_moved",
                           "conditions":[],"actions":[{"type":"comment","text":"rule result"}],
                           "enabled":True}}
        self.request("/api/collab", command, self.owner)
        self.assertEqual(len(self.request("/api/rules?projectId=p-sample",token=self.owner)["items"]), 1)
        with self.assertRaises(HTTPError) as error:
            self.request("/api/rules?projectId=p-sample",token=self.viewer)
        self.assertEqual(error.exception.code, 403)
        self.assertIn("new",self.request("/api/scheduler", {"run":True},self.owner)["result"])
        with self.assertRaises(HTTPError) as error:
            self.request("/api/scheduler", {"run":True},self.viewer)
        self.assertEqual(error.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
