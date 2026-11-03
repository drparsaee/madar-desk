"""Bridge regression: real packaged native_app, not only source-hosted accounting."""
from datetime import datetime, timezone
import unittest
from unittest.mock import patch

import native_app


class PackagedAccountingUpdateTests(unittest.TestCase):
    def test_accounting_page_native_bridge_exports_three_safe_update_methods(self):
        js = native_app.ACCOUNTING_JS_BRIDGE
        for name in ("releaseCheck", "releaseDownload", "releaseInstall"):
            self.assertIn("'" + name + "'", js)
            self.assertTrue(callable(getattr(native_app.Bridge, name, None)))
        # Reduced accounting wrapper must not export task-state mutation APIs.
        for name in ("'saveState'", "'getState'", "'lanSaveUser'", "'financeCommand'"):
            self.assertNotIn(name, js)

    def test_packaged_bridge_host_date_matches_company_fixed_offset(self):
        class FakeDatetime:
            @staticmethod
            def now(_tz):
                return datetime(2026, 11, 2, 22, 0, tzinfo=timezone.utc)

        with patch.object(native_app, "datetime", FakeDatetime):
            utc = native_app.Bridge._with_company_posting_today({
                "view": {"companyProfile": None}})
            iran = native_app.Bridge._with_company_posting_today({
                "view": {"companyProfile": {
                    "postingUtcOffsetMinutes": 210,
                    "postingCalendarMode": "fixed-offset-no-dst"}}})
        self.assertEqual(utc["postingToday"], "2026-11-02")
        self.assertEqual(iran["postingToday"], "2026-11-03")

    def test_lan_accounting_get_uses_server_side_bridge_for_calendar(self):
        from pathlib import Path
        source = (Path(__file__).parents[1] / "lan.py").read_text(encoding="utf8")
        self.assertIn("return self.bridge._standalone_accounting_read_local(", source)
        self.assertIn("return self.bridge._standalone_accounting_command_local(", source)


if __name__ == "__main__":
    unittest.main()
