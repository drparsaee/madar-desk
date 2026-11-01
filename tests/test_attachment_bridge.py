import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import native_app
from lan import LanService


class AttachmentBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.patch=patch.object(native_app,"datadir",return_value=self.root)
        self.patch.start()
        self.bridge=native_app.Bridge()
        # Explicit historical scenario. Customer first-run must stay empty.
        self.bridge.saveState(native_app.initial_state())
        self.content=base64.b64encode("متن تایید شده\n".encode("utf8")).decode("ascii")

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_solo_upload_read_preview_delete_and_file_link_independence(self):
        result=self.bridge.attachmentUpload("example-2","notes.txt",self.content,"solo-upload")
        self.assertEqual(result["mime"],"text/plain")
        self.assertEqual(self.bridge.attachmentUpload("example-2","notes.txt",self.content,"solo-upload"),result)
        self.assertEqual(len(self.bridge.attachmentList("example-2")),1)
        self.assertEqual(self.bridge.attachmentPreview(result["id"])["kind"],"plain-text")
        self.assertEqual(self.bridge.attachmentRead(result["id"])["contentBase64"],self.content)
        self.assertEqual(self.bridge.getState()["tasks"][1]["fileLinks"],[])
        deleted=self.bridge.attachmentDelete(result["id"],"solo-delete")
        self.assertTrue(deleted["deleted"])
        self.assertEqual(self.bridge.attachmentList("example-2"),[])

    def test_lan_authentication_role_and_project_scope(self):
        service=LanService(self.bridge,self.root/"users.json",bind="127.0.0.1",port=0)
        service.setup_owner("boss","secure-admin-password")
        admin=service.authenticate("boss","secure-admin-password")["token"]
        service.upsert_user(admin,{"username":"writer","password":"secure-editor-password",
                                  "role":"editor","projects":["p-sample"]})
        service.upsert_user(admin,{"username":"viewer","password":"secure-viewer-password",
                                  "role":"viewer","projects":["p-sample"]})
        writer=service.authenticate("writer","secure-editor-password")["token"]
        viewer=service.authenticate("viewer","secure-viewer-password")["token"]
        data={"kind":"upload","cardId":"example-2","filename":"report.txt",
              "contentBase64":self.content,"requestId":"editor-upload"}
        item=service.attachment_action(writer,"upload",payload=data)
        self.assertEqual(service.attachment_action(viewer,"list",card_id="example-2")[0]["id"],item["id"])
        self.assertEqual(service.attachment_action(viewer,"read",attachment_id=item["id"])["contentBase64"],self.content)
        with self.assertRaises(PermissionError):
            service.attachment_action(viewer,"delete",payload={"kind":"delete","attachmentId":item["id"],"requestId":"no"})
        with self.assertRaises(PermissionError):
            service.attachment_action(viewer,"upload",payload=data|{"requestId":"different"})
        service.upsert_user(admin,{"username":"foreign","password":"secure-foreign-password",
                                  "role":"editor","projects":["p-personal"]})
        foreign=service.authenticate("foreign","secure-foreign-password")["token"]
        with self.assertRaises(PermissionError):
            service.attachment_action(foreign,"read",attachment_id=item["id"])


if __name__=="__main__":
    unittest.main()
