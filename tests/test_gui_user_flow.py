"""Safety and route contract tests for the isolated GUI interaction helper.

The fake window recognizes only the documented current selectors; it does not
pretend to be a WebView2 test. The real route still needs a rebuilt EXE smoke.
"""
from __future__ import annotations

from copy import deepcopy
from itertools import count
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import gui_user_flow


class SyntheticBridge:
    def __init__(self, appdata, currency="RIAL"):
        self.connection = {"mode": "solo"}
        self.path = appdata / "madar-tasks.json"
        self.finance = {"documents": []}
        self.view = {"currency": currency, "revision": 0}
        self.tasks = []

    def _load_finance(self):
        return deepcopy(self.finance)

    def standaloneAccountingRead(self):
        return {"view": deepcopy(self.view)}

    def getState(self):
        return {"tasks": deepcopy(self.tasks)}


class SyntheticWindow:
    def __init__(self, bridge, *, mutate_ledger_on_exit=False):
        self.bridge = bridge
        self.path = "/"
        self.tab = "overview"
        self.dialog = False
        self.drawer = False
        self.actions = []
        self.mutate_ledger_on_exit = mutate_ledger_on_exit

    def evaluate_js(self, script):
        if "location.pathname==='/'" in script:
            return self.path == "/"
        if ".vitrea-primary-nav button')].some" in script:
            return self.path == "/"
        if "x=>x.textContent.includes('حسابداری')" in script and "b.click()" in script:
            self.actions.append("enter_accounting")
            self.path = "/accounting.html"
            return True
        if "location.pathname==='/accounting.html'" in script:
            return self.path == "/accounting.html"
        if "sac-vtr-home" in script:
            return self.path == "/accounting.html" and self.tab == "overview"
        if "sac-sidebar-footer strong" in script:
            return self.path == "/accounting.html" and self.bridge.view["currency"] == "RIAL"
        if "b=>b.textContent.includes('دریافت، پرداخت و اقساط')" in script and "btn.click()" in script:
            self.tab = "settlements"
            return True
        if "b=>b.textContent.includes('گزارش‌های مالی')" in script and "btn.click()" in script:
            self.tab = "reports"
            return True
        if "sac-header h1" in script and "دریافت، پرداخت و اقساط" in script:
            return self.tab == "settlements"
        if "sac-header h1" in script and "گزارش‌های مالی" in script:
            return self.tab == "reports"
        if "btn.textContent.includes('خروج از حسابداری')" in script:
            self.actions.append("exit_accounting")
            self.path = "/index.html"
            if self.mutate_ledger_on_exit:
                self.bridge.view["revision"] += 1
            return True
        if "location.pathname==='/index.html'" in script:
            return self.path == "/index.html"
        if "const btn=document.querySelector('.create-primary')" in script:
            self.actions.append("open_task")
            self.dialog = True
            return True
        if "form.task-create" in script:
            return self.dialog
        if "HTMLInputElement.prototype" in script:
            self.actions.append("fill_task")
            return True
        if "button[type=submit]" in script:
            self.actions.append("save_task")
            self.bridge.tasks.append({"title": gui_user_flow.TASK_TITLE})
            self.drawer = True
            return True
        if "task-edit-title" in script:
            return self.drawer
        raise AssertionError("Unrecognized GUI probe: " + script[:140])


class GuiUserFlowTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix=".qa-v1-gui-isolated-")
        self.addCleanup(self.scratch.cleanup)
        root = Path(self.scratch.name)
        appdata = root / "AppData" / "Roaming"
        localappdata = root / "AppData" / "Local"
        webview = root / "WebView2"
        for folder in (appdata, localappdata, webview):
            folder.mkdir(parents=True)
        environment = {
            "MADAR_RELEASE_QA": "1",
            "MADAR_QA_INTERACTION": "1",
            "MADAR_QA_VIEW": "sample-project",
            "MADAR_QA_REPORT": str(root / "diagnostics.json"),
            "APPDATA": str(appdata),
            "LOCALAPPDATA": str(localappdata),
            "WEBVIEW2_USER_DATA_FOLDER": str(webview),
        }
        self.env = patch.dict(os.environ, environment)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.bridge = SyntheticBridge(appdata)

    def test_successful_synthetic_navigation_is_safe_and_creates_one_task(self):
        window = SyntheticWindow(self.bridge)
        result = gui_user_flow.run_ui_flow(window, self.bridge)
        self.assertTrue(all(x["pass"] for x in result.values()), result)
        self.assertEqual(window.actions,
                         ["enter_accounting", "exit_accounting", "open_task", "fill_task", "save_task"])
        self.assertEqual(result["task_saved_to_host"]["observed"], 1)
        self.assertEqual(self.bridge.view, {"currency": "RIAL", "revision": 0})

    def test_toman_head_aborts_before_any_navigation_or_mutation(self):
        self.bridge.view["currency"] = "TOMAN"
        window = SyntheticWindow(self.bridge)
        result = gui_user_flow.run_ui_flow(window, self.bridge)
        self.assertFalse(result["standalone_currency_rial_head"]["pass"])
        self.assertNotIn("accounting_workspace_opens", result)
        self.assertEqual(window.actions, [])
        self.assertEqual(self.bridge.tasks, [])

    def test_changed_independent_ledger_blocks_task_creation(self):
        window = SyntheticWindow(self.bridge, mutate_ledger_on_exit=True)
        result = gui_user_flow.run_ui_flow(window, self.bridge)
        self.assertTrue(result["finance_unchanged"]["pass"])
        self.assertFalse(result["standalone_unchanged"]["pass"])
        self.assertEqual(window.actions, ["enter_accounting", "exit_accounting"])
        self.assertNotIn("task_saved_to_host", result)
        self.assertEqual(self.bridge.tasks, [])

    def test_task_save_waits_until_authoritative_host_reports_persisted_card(self):
        original = self.bridge.getState
        reads = 0

        def delayed_read():
            nonlocal reads
            reads += 1
            if reads < 4:
                return {"tasks": []}
            return original()

        self.bridge.getState = delayed_read
        result = gui_user_flow.run_ui_flow(SyntheticWindow(self.bridge), self.bridge)
        self.assertEqual(reads, 4)
        self.assertTrue(result["task_saved_to_host"]["pass"])

    def test_task_drawer_does_not_pass_when_host_never_persists(self):
        self.bridge.getState = lambda: {"tasks": []}
        # Advance the deadline without spending eight real seconds in a unit test.
        with patch.object(gui_user_flow.time, "monotonic", side_effect=count(start=0, step=1)), \
             patch.object(gui_user_flow.time, "sleep"):
            result = gui_user_flow.run_ui_flow(SyntheticWindow(self.bridge), self.bridge)
        self.assertTrue(result["new_task_drawer"]["pass"])
        self.assertFalse(result["task_saved_to_host"]["pass"])
        self.assertEqual(result["task_saved_to_host"]["observed"], 0)

    def test_nonisolated_appdata_is_rejected_before_dom_probe(self):
        with patch.dict(os.environ, {"APPDATA": str(Path(self.scratch.name) / "foreign") }):
            with self.assertRaisesRegex(RuntimeError, "APPDATA is not"):
                gui_user_flow.run_ui_flow(SyntheticWindow(self.bridge), self.bridge)


if __name__ == "__main__":
    unittest.main()
