import re
import unittest

import native_app


class JsBridgeExposureTests(unittest.TestCase):
    def test_every_interactive_ui_backend_method_is_exported(self):
        required = {
            "getState", "getStateForUi", "saveState",
            "cloudPeerStatus", "cloudPeerConfigure", "cloudPeerGenerate", "cloudPeerForget",
            "runDueScheduler",
            "attachmentList", "attachmentPreview", "attachmentRead", "attachmentUpload",
            "attachmentDelete", "attachmentBackup",
            "createUnifiedSqliteBackup",
            "collabRead", "collabCommand", "syncStatus",
        }
        quoted = set(re.findall(r"['\"]([A-Za-z]+)['\"]", native_app.JS_BRIDGE))
        self.assertFalse(required - quoted, f"React calls methods that window.madar does not export: {required - quoted}")
        self.assertTrue(all(callable(getattr(native_app.Bridge, name, None))
                            for name in required))
        # Finance mutations/read APIs were deliberately retired from Madar.
        # They remain fail-closed native shims and MUST NOT be JS-exported.
        retired = {"financeRead", "financeStatus", "financeCommand",
                   "accountingRead", "accountingCommand"}
        self.assertFalse(retired & quoted)
        self.assertTrue(all(callable(getattr(native_app.Bridge, name, None))
                            for name in retired))


if __name__ == "__main__":
    unittest.main()
