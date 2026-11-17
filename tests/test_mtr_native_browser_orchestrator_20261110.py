"""Contract tests for the optional real-React -> packaged-Taraz QA handoff.

Mocks explicitly prevent launching either installed GUI or a browser. These
tests do not claim end-to-end acceptance; that requires the independent
`qa_mtr_two_ui_local_cycle_20261110.py --native-browser` process exit 0.
"""
import importlib.util
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
import unittest
from unittest.mock import patch


SCRIPT = (Path(__file__).resolve().parents[1] / "scripts" /
          "qa_mtr_two_ui_local_cycle_20261110.py")
SPEC = importlib.util.spec_from_file_location("mtr_native_browser_orchestrator", SCRIPT)
QA = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(QA)


class NativeBrowserOrchestratorContracts(unittest.TestCase):
    def test_native_mode_requires_real_boolean_before_launch(self):
        with patch.object(QA, "_load_script") as loader:
            for mode in ("true", 1, [], None):
                with self.subTest(mode=repr(mode)):
                    with self.assertRaises(TypeError):
                        QA.run(native_browser=mode)
            loader.assert_not_called()

    def test_synthetic_user_click_callback_routes_native_flag_and_decision(self):
        proposal_id = "d" * 32
        card = MappingProxyType({
            "id": "synthetic-task", "projectId": "synthetic-project",
            "title": "Synthetic nonfinancial request",
        })
        bridge = Path("C:/synthetic/sandbox/AppData/Local/Madar-Taraz-Bridge")
        observed = []

        def gui_run(*, send_once_ui, on_disposable_proposal_ready):
            self.assertIs(send_once_ui, True)
            result = on_disposable_proposal_ready(bridge, proposal_id, card)
            return {"tarazCycle": result}

        def browser_run(root, identifier, task, *, decision, native_browser):
            observed.append((root, identifier, task, decision, native_browser))
            return {"reviewed": decision == "reviewed", "native": native_browser}

        with (patch.object(QA, "_load_script", return_value=SimpleNamespace(run=gui_run))
              as loader,
              patch.object(QA, "_review_with_installed_taraz_and_real_browser",
                           side_effect=browser_run)):
            for decision in ("reviewed", "rejected"):
                outcome = QA.run(decision=decision, native_browser=True)
                self.assertEqual(outcome["tarazCycle"],
                                 {"reviewed": decision == "reviewed", "native": True})
        self.assertEqual(loader.call_count, 2)
        self.assertEqual([item[3] for item in observed], ["reviewed", "rejected"])
        self.assertTrue(all(item[0] == bridge and item[1] == proposal_id and
                            item[2] is card and item[4] is True for item in observed))

    def test_native_browser_callback_error_propagates_not_success(self):
        def gui_run(*, send_once_ui, on_disposable_proposal_ready):
            self.assertTrue(send_once_ui)
            return on_disposable_proposal_ready(
                Path("C:/synthetic/bridge"), "a" * 32,
                MappingProxyType({"id": "qa", "projectId": "p", "title": "QA"}))

        with (patch.object(QA, "_load_script", return_value=SimpleNamespace(run=gui_run)),
              patch.object(QA, "_review_with_installed_taraz_and_real_browser",
                           side_effect=RuntimeError("synthetic native review denied"))):
            with self.assertRaisesRegex(RuntimeError, "synthetic native review denied"):
                QA.run(native_browser=True)


if __name__ == "__main__":
    unittest.main()
