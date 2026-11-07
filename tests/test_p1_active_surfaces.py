"""Synthetic contracts for *active* Madar desktop/UI/LAN surfaces.

Legacy accounting display keys may remain in historical LAN profile records;
they are not active UI features, and never grant host authorization.
No real profiles, packaged executables, or remote services are used here.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import native_app
from lan import LanService
from role_profiles import DISPLAY_FEATURE_TIERS, effective_display


ROOT = Path(__file__).resolve().parent.parent
RETIRED_FINANCE_METHODS = frozenset({
    "financeRead", "financeStatus", "financeCommand",
})
RETIRED_DISPLAY_KEYS = frozenset({
    "financeHub", "projectFinance", "profitPeek", "taskCostControls",
    "checklistCostControls", "projectPricing", "accountingDashboard",
})
# These entry points use the web API, not the Windows pywebview bridge.
WEB_ONLY_MODULES = frozenset({
    "web_sync_dialog.jsx", "web_sync_engine.mjs", "web_backup_dialog.jsx",
})
WEB_ONLY_APP_METHODS = frozenset({"webSyncNow"})
# The imported module still contains a historical OrderSaleFields component,
# but the active card editors import only its StageExpenseFields component.
HISTORICAL_ORDER_COMPONENT = "order_finance_fields.jsx"


def _node(script: str, *args: str) -> object:
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script, *args],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=20, check=False,
    )
    if completed.returncode:
        raise AssertionError(
            f"Isolated Node contract failed ({completed.returncode}): "
            + completed.stderr[-1500:]
        )
    return json.loads(completed.stdout)


def _local_import_graph(entry: Path) -> dict[Path, str]:
    """Follow local, statically imported JS/JSX, not unused sibling files."""
    pending = [entry]
    visited: dict[Path, str] = {}
    statement = re.compile(
        r"(?ms)^\s*import\s+(?:(?!;).)*?\s+from\s+['\"](\.[^'\"]+)['\"]\s*;"
    )
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        source = path.read_text(encoding="utf-8")
        visited[path] = source
        for relative in statement.findall(source):
            base = path.parent / relative
            for candidate in (
                base, Path(str(base) + ".js"), Path(str(base) + ".jsx"),
                Path(str(base) + ".mjs"),
            ):
                if candidate.is_file() and candidate.suffix in {".js", ".jsx", ".mjs"}:
                    pending.append(candidate)
                    break
    return visited


class _DisposableTaskBridge:
    def __init__(self):
        self._lock = threading.RLock()

    def getState(self):
        return {"projects": [], "tasks": []}


class _ClosingEvent:
    def __iadd__(self, callback):
        self.callback = callback
        return self


class _BackupStub:
    def __init__(self, *_args, **_kwargs):
        pass

    def start(self):
        pass

    def stop(self):
        pass


class ActiveBridgeTests(unittest.TestCase):
    def test_runtime_bridge_exports_reachable_task_methods_and_no_finance(self):
        # Evaluate the actual script, not a guessed list of API names.
        bridge_script = native_app.JS_BRIDGE.replace("<script>", "").replace("</script>", "")
        exported = set(_node(
            """
            import vm from 'node:vm';
            const scope={window:{pywebview:{api:{}}}};
            vm.runInNewContext(JSON.parse(process.argv[1]),scope);
            console.log(JSON.stringify(Object.keys(scope.window.madar)));
            """,
            json.dumps(bridge_script),
        ))
        self.assertIn("getState", exported)
        self.assertIn("saveState", exported)
        self.assertIn("tarazIntegrationStatus", exported)
        self.assertIn("tarazIntegrationQueue", exported)
        self.assertTrue(RETIRED_FINANCE_METHODS.isdisjoint(exported))
        self.assertNotIn("standaloneAccountingRead", exported)
        self.assertNotIn("standaloneAccountingCommand", exported)

        app_source = (ROOT / "src" / "App.jsx").read_text(encoding="utf-8")
        direct_calls = set(re.findall(r"\bapi\.([A-Za-z_]\w*)\s*\(", app_source))
        self.assertIn("webSyncNow", direct_calls)
        # The only non-desktop App call is explicitly guarded as web-only.
        self.assertRegex(app_source, r"if\s*\(isWebApp[^\n]*\)\s*syncResult=await api\.webSyncNow")
        self.assertEqual(
            set(), direct_calls - WEB_ONLY_APP_METHODS - exported,
            "Active native App method calls must be exported by window.madar",
        )
        self.assertTrue(
            all(callable(getattr(native_app.Bridge, name, None))
                for name in direct_calls - WEB_ONLY_APP_METHODS),
            "Every exported and directly used task method needs a native host implementation",
        )

    def test_imported_active_task_components_have_a_native_bridge_contract(self):
        graph = _local_import_graph(ROOT / "src" / "App.jsx")
        self.assertIn(ROOT / "src" / "teamplus.jsx", graph)
        self.assertIn(ROOT / "src" / HISTORICAL_ORDER_COMPONENT, graph)
        app = graph[ROOT / "src" / "App.jsx"]
        self.assertNotRegex(app, r"(?m)^import\b[^;]*finance(?:panel|overview)")
        self.assertNotRegex(
            "\n".join(source for source in graph.values()),
            r"\b<OrderSaleFields\b",
            "Old accounting quote/read UI must not be mounted from task components",
        )
        bridge = set(re.findall(
            r"'([A-Za-z_]\w*)'", native_app.JS_BRIDGE.split(".map(key")[0],
        ))
        calls: set[str] = set()
        for path, source in graph.items():
            if path.name in WEB_ONLY_MODULES | {HISTORICAL_ORDER_COMPONENT}:
                continue
            calls.update(re.findall(r"\bapi\.([A-Za-z_]\w*)\s*\(", source))
        self.assertEqual(
            set(), calls - WEB_ONLY_APP_METHODS - bridge,
            "An imported, potentially reachable task component calls a method "
            "missing from the native bridge",
        )

    def test_dormant_finance_pages_not_imported_and_retired_host_methods_denied(self):
        app = (ROOT / "src" / "App.jsx").read_text(encoding="utf-8")
        imports = _local_import_graph(ROOT / "src" / "App.jsx")
        for dormant in ("financepanel.jsx", "financeoverview.jsx"):
            self.assertNotIn(ROOT / "src" / dormant, imports)
            self.assertNotRegex(app, r"(?m)^\s*import\b[^;]*" + re.escape(dormant))
        for name in RETIRED_FINANCE_METHODS:
            with self.subTest(name=name):
                self.assertTrue(callable(getattr(native_app.Bridge, name)))
                with self.assertRaises(PermissionError):
                    getattr(native_app.Bridge, name)(object())

    def test_local_native_html_rejects_accounting_document_even_if_present(self):
        # Boot the real native loopback StaticHandler using ONLY test-generated
        # HTML and a fake window. No installed EXE or real WebView2.
        with tempfile.TemporaryDirectory(prefix="madar-p1-active-html-") as tmp:
            root = Path(tmp)
            site = root / "dist"
            site.mkdir()
            (site / "index.html").write_text(
                "<html><head></head><body>TEST TASK PAGE</body></html>", encoding="utf-8",
            )
            (site / "accounting.html").write_text(
                "<html>PRIVATE ACCOUNTING PAGE SHOULD NOT LEAK</html>", encoding="utf-8",
            )
            fake = SimpleNamespace(
                connection={"mode": "solo"}, _lock=threading.RLock(),
                _exit_financial_locked=False,
                startScheduledJobs=lambda: None, stopScheduledJobs=lambda: None,
            )
            window = SimpleNamespace(events=SimpleNamespace(
                closing=_ClosingEvent(), loaded=_ClosingEvent(),
            ))

            def check_server(_title, url, **_kwargs):
                with urlopen(url, timeout=4) as response:
                    html = response.read().decode("utf-8")
                    self.assertIn("TEST TASK PAGE", html)
                    self.assertIn("window.madar", html)
                return window

            def check_urls(**_kwargs):
                # The create_window URL was already probed. Reuse its value.
                for path in ("/accounting.html", "/subdir/accounting.html"):
                    with self.subTest(path=path):
                        with self.assertRaises(HTTPError) as failure:
                            urlopen(window._url + path, timeout=4)
                        self.assertEqual(failure.exception.code, 404)

            def fake_create_window(_title, url, **kwargs):
                window._url = url.rstrip("/")
                return check_server(_title, url, **kwargs)

            import host_backup_scheduler
            import standalone_accounting_desktop
            with (
                patch.object(native_app.sys, "_MEIPASS", str(root), create=True),
                patch.dict("os.environ", {
                    "APPDATA": str(root / "private-profile"),
                    "LOCALAPPDATA": str(root / "private-profile"),
                    "MADAR_QA_REPORT": "",
                }),
                patch.object(native_app, "Bridge", return_value=fake),
                patch.object(native_app.webview, "create_window", side_effect=fake_create_window),
                patch.object(native_app.webview, "start", side_effect=check_urls),
                patch.object(host_backup_scheduler, "HostBackupScheduler", _BackupStub),
                patch.object(
                    standalone_accounting_desktop, "NativeAccountingCloseGate",
                    return_value=SimpleNamespace(closing=lambda: False),
                ),
            ):
                native_app.main()


class ActiveRoleAndLanTests(unittest.TestCase):
    def test_active_presentation_tiers_match_server_subset_not_full_legacy_catalog(self):
        client = _node(
            """
            import {INTERFACE_FEATURE_TIERS} from './src/interface_mode.js';
            console.log(JSON.stringify(INTERFACE_FEATURE_TIERS));
            """
        )
        self.assertTrue(client)
        self.assertTrue(set(client).issubset(DISPLAY_FEATURE_TIERS))
        self.assertEqual(
            client,
            {name: tier for name, tier in DISPLAY_FEATURE_TIERS.items() if name in client},
            "Current shared features must agree on display tiers",
        )
        self.assertTrue(RETIRED_DISPLAY_KEYS.issubset(DISPLAY_FEATURE_TIERS))
        self.assertTrue(RETIRED_DISPLAY_KEYS.isdisjoint(client))

    def test_old_finance_grants_are_preserved_as_data_but_never_rendered_or_authorize(self):
        # An old admin or a custom account profile may legitimately retain
        # retired display-feature keys. This is not a license to expose them.
        account = {
            "role": "admin", "displayRole": "superadmin",
            "displayMode": "finance", "displayFeatures": [
                "cards", "planner", *sorted(RETIRED_DISPLAY_KEYS),
            ],
        }
        role = effective_display(account)
        self.assertTrue(RETIRED_DISPLAY_KEYS.issubset(set(role["displayFeatures"])))
        result = _node(
            """
            import {resolvedDisplayScope,isManagedFeatureVisible} from './src/managed_display.js';
            const user=JSON.parse(process.argv[1]);
            const scope=resolvedDisplayScope({mode:'client', user});
            const keys=['cards','planner','createProject',
              'financeHub','projectFinance','profitPeek','taskCostControls',
              'checklistCostControls','projectPricing','accountingDashboard'];
            const visible=Object.fromEntries(keys.map(key=>[
              key,isManagedFeatureVisible(scope,key,{canManage:false,canEdit:false})
            ]));
            console.log(JSON.stringify({scope,visible}));
            """,
            json.dumps({"role": "viewer", **role}),
        )
        self.assertTrue(result["visible"]["cards"])
        self.assertTrue(result["visible"]["planner"])
        self.assertFalse(result["visible"]["createProject"])
        for retired in RETIRED_DISPLAY_KEYS:
            self.assertFalse(result["visible"][retired], retired)
            self.assertNotIn(retired, result["scope"]["features"])

    def test_synthetic_lan_viewer_finance_presentation_never_grants_task_acl_or_finance_routes(self):
        with tempfile.TemporaryDirectory(prefix="madar-p1-lan-roles-") as tmp:
            service = LanService(
                _DisposableTaskBridge(), Path(tmp) / "lan-users.json",
                bind="127.0.0.1", port=0,
            )
            service.setup_owner("owner", "owner-secure-123")
            base = f"http://127.0.0.1:{service.start()}"
            self.addCleanup(service.stop)

            def request(path, payload=None, token=None):
                data = (json.dumps(payload).encode("utf-8")
                        if payload is not None else None)
                headers = {"Content-Type": "application/json"}
                if token is not None:
                    headers["Authorization"] = "Bearer " + token
                with urlopen(Request(base + path, data=data, headers=headers),
                             timeout=6) as response:
                    return json.loads(response.read())

            admin = request("/api/login", {
                "username": "owner", "password": "owner-secure-123",
            })["token"]
            old_role = {
                "id": "historic-finance", "label": "Historical display role",
                "displayMode": "finance",
                "features": ["cards", "planner", "projectFinance", "financeHub"],
            }
            request("/api/display-roles", old_role, admin)
            request("/api/user", {
                "username": "viewer", "password": "long-password-123",
                "role": "viewer", "projects": None,
                "displayRole": "historic-finance",
                "displayFeatures": ["cards", "planner", "projectFinance", "financeHub"],
            }, admin)
            token = request("/api/login", {
                "username": "viewer", "password": "long-password-123",
            })["token"]
            account = request("/api/me", token=token)["user"]
            self.assertEqual(account["role"], "viewer")
            self.assertIn("financeHub", account["displayFeatures"])
            # Presentation flags never elevate server role or restore
            # deliberately retired HTTP endpoints.
            cases = [
                ("/api/users", 403),
                ("/api/display-roles", 403),
                ("/api/finance", 404),
                ("/api/finance-status", 404),
                ("/api/finance-overview", 404),
                ("/api/standalone-accounting", 404),
            ]
            for path, expected in cases:
                with self.subTest(path=path):
                    with self.assertRaises(HTTPError) as failure:
                        request(path, token=token)
                    self.assertEqual(failure.exception.code, expected)


if __name__ == "__main__":
    unittest.main()
