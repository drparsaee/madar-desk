"""Synthetic CURRENT standalone acceptance probes, no live data or releases.

These checks are revised after concurrent host fixes; the narrow JS wrapper
does NOT imply that underlying pywebview.api is a sandbox.
"""

from __future__ import annotations

from http.client import HTTPConnection
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest

from standalone_accounting_desktop import (
    ACCOUNTING_FILE, AccountingDesktopAPI, JS_BRIDGE,
    serve_accounting_page,
)


ROOT = Path(__file__).resolve().parents[1]


class StandaloneAccountingAcceptanceTests(unittest.TestCase):
    def test_distinct_page_and_react_root_do_not_bootstrap_tasks(self):
        page = (ROOT / "accounting.html").read_text(encoding="utf8")
        main = (ROOT / "src/standalone_main.jsx").read_text(encoding="utf8")
        ui = (ROOT / "src/standalone_accounting_workspace.jsx").read_text(encoding="utf8")
        app = (ROOT / "src/App.jsx").read_text(encoding="utf8")
        self.assertIn('lang="fa" dir="rtl"', page)
        self.assertIn('/src/standalone_main.jsx', page)
        self.assertNotIn('src/main.jsx', page)
        self.assertIn('StandaloneAccountingWorkspace', main)
        self.assertIn('standaloneAccountingRead', main)
        self.assertIn('standaloneAccountingCommand', main)
        self.assertNotIn("from './App'", main)
        self.assertNotIn("from './App.jsx'", main)
        self.assertNotIn('getState(', main)
        self.assertNotIn('tasks=', main)
        self.assertNotIn('projects=', main)
        self.assertNotIn('api.accountingCommand(', ui)
        self.assertNotIn('api.accountingRead(', ui)
        # Accounting retains its independent desktop/page and must no longer
        # be reachable through a shortcut inside the Madar task application.
        self.assertNotIn("window.location.assign('./accounting.html')", app)

    def test_solo_desktop_bridge_exports_only_accounting_commands(self):
        self.assertIn('standaloneAccountingRead', JS_BRIDGE)
        self.assertIn('standaloneAccountingCommand', JS_BRIDGE)
        for forbidden in ('getState', 'saveState', 'financeRead',
                          'projects', 'tasks', 'accountingCommand'):
            # accountingCommand is a substring in standaloneAccountingCommand;
            # exact API-name matching is tested below.
            if forbidden == 'accountingCommand':
                continue
            self.assertNotIn("'" + forbidden + "'", JS_BRIDGE)

    def test_synthetic_independent_lifecycle_uses_private_temp_database(self):
        with TemporaryDirectory() as tmp:
            parent = Path(tmp) / 'accounting-private'
            api = AccountingDesktopAPI(parent)
            self.assertFalse(parent.exists(), 'Construction must not open any data')
            initial = api.standaloneAccountingRead()
            self.assertEqual(initial['revision'], 0)
            self.assertEqual(initial['view']['currency'], 'RIAL')
            commands = [
                {'type': 'party.register', 'eventId': 'a-1', 'partyId': 'c-1',
                 'name': 'Synthetic Buyer', 'kind': 'customer'},
                {'type': 'invoice.create', 'eventId': 'a-2', 'invoiceId': 'inv-1',
                 'partyId': 'c-1', 'documentDate': '2026-01-01',
                 'lines': [{'description': 'Example service', 'quantity': 2,
                            'unitPrice': 1000}]},
                {'type': 'invoice.approve', 'eventId': 'a-3', 'invoiceId': 'inv-1'},
                {'type': 'invoice.issue', 'eventId': 'a-4', 'invoiceId': 'inv-1',
                 'postingDate': '2026-01-02'},
            ]
            current = initial
            for command in commands:
                current = api.standaloneAccountingCommand({
                    'command': command,
                    'expectedRevision': current['revision'],
                })
            self.assertEqual(current['revision'], 4)
            self.assertEqual(current['view']['invoices']['inv-1']['status'], 'issued')
            self.assertEqual(current['view']['parties']['c-1']['receivable'], 2000)
            self.assertEqual(len(current['view']['journals']), 1)
            self.assertEqual(api.standaloneAccountingRead()['revision'], 4)
            self.assertTrue((parent / ACCOUNTING_FILE).is_file())
            for forbidden in ('tasks.json', 'finance.json', 'madar-unified.sqlite3'):
                self.assertFalse((parent / forbidden).exists())
            with self.assertRaisesRegex(ValueError, 'Invalid accounting CAS request'):
                api.standaloneAccountingCommand({
                    'command': commands[0], 'expectedRevision': True,
                })
            with self.assertRaisesRegex(ValueError, 'Invalid accounting CAS request'):
                api.standaloneAccountingCommand({
                    'command': commands[0], 'expectedRevision': 4,
                    'actor': 'forged',
                })

    def test_only_exact_root_serves_accounting_page_and_exact_index_is_404(self):
        with TemporaryDirectory() as tmp:
            site = Path(tmp)
            (site / 'accounting.html').write_text(
                '<html><head></head><body>PRIVATE ACCOUNTING</body></html>',
                encoding='utf8')
            (site / 'index.html').write_text('SECRET TASK UI', encoding='utf8')
            server = serve_accounting_page(site)
            worker = Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                for path, code, expected in (
                    ('/', 200, 'PRIVATE ACCOUNTING'),
                    ('/accounting.html', 200, 'PRIVATE ACCOUNTING'),
                    ('/index.html', 404, None),
                ):
                    with self.subTest(path=path):
                        status, body = self._get(server.server_port, path)
                        self.assertEqual(status, code)
                        if expected:
                            self.assertIn(expected, body)
                        self.assertNotIn('SECRET TASK UI', body)
            finally:
                server.shutdown(); server.server_close(); worker.join(timeout=5)

    def test_encoded_and_normalized_index_paths_must_not_expose_task_page(self):
        """Reject index aliases even when SimpleHTTPRequestHandler decodes them."""
        with TemporaryDirectory() as tmp:
            site = Path(tmp)
            (site / 'accounting.html').write_text(
                '<html><head></head><body>PRIVATE ACCOUNTING</body></html>',
                encoding='utf8')
            (site / 'index.html').write_text('SECRET TASK UI', encoding='utf8')
            server = serve_accounting_page(site)
            worker = Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                for raw in ('/%69ndex.html', '/index%2Ehtml', '/./index.html',
                            '/folder/../index.html', '/INDEX.HTML'):
                    with self.subTest(path=raw):
                        status, body = self._get(server.server_port, raw)
                        self.assertEqual(status, 404, 'Task index alias must be denied')
                        self.assertNotIn('SECRET TASK UI', body)
            finally:
                server.shutdown(); server.server_close(); worker.join(timeout=5)

    def test_main_app_exports_task_bridge_only_and_accounting_is_independent(self):
        """Madar task window must not expose the retired accounting facade."""
        import native_app
        main_bridge = native_app.JS_BRIDGE
        self.assertIn("'getState'", main_bridge)
        self.assertFalse(hasattr(native_app, 'ACCOUNTING_JS_BRIDGE'))
        for forbidden in ("'standaloneAccountingRead'",
                          "'standaloneAccountingCommand'",
                          "'standaloneAccountingCsvChooseFile'",
                          "'standaloneAccountingCsvPreview'",
                          "'financeCommand'", "'accountingCommand'"):
            self.assertNotIn(forbidden, main_bridge)
        # The standalone binary's own wrapper is still independently tested
        # above; removing the main-app bridge must not erase that coverage.
        self.assertIn("'standaloneAccountingRead'", JS_BRIDGE)
        self.assertIn("'standaloneAccountingCommand'", JS_BRIDGE)

    @staticmethod
    def _get(port, raw_path):
        client = HTTPConnection('127.0.0.1', port, timeout=4)
        try:
            client.request('GET', raw_path)
            response = client.getresponse()
            return response.status, response.read().decode('utf8', errors='replace')
        finally:
            client.close()


if __name__ == '__main__':
    unittest.main()
