"""Static/isolated protocol checks; no real Windows process is launched."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('madar_gui_smoke', PROJECT / 'scripts' / 'v1_gui_smoke.py')
gui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gui)
flow_spec = importlib.util.spec_from_file_location(
    'madar_gui_user_flow', PROJECT / 'gui_user_flow.py')
user_flow = importlib.util.module_from_spec(flow_spec)
flow_spec.loader.exec_module(user_flow)


class FakeBridge:
    """Records no finance writes; all data belongs to a synthetic path."""
    def __init__(self, profile):
        self.connection = {'mode': 'solo'}
        self.path = profile / 'MadarDesk' / 'tasks.json'
        self.finance = {'accounting': {'events': []}, 'testUnit': 'TOMAN'}
        self.tasks = [{'id': 'synthetic-1', 'title': user_flow.TASK_TITLE}]
        self.finance_reads = 0
        self.state_reads = 0

    def _load_finance(self):
        self.finance_reads += 1
        return self.finance.copy()

    def getState(self):
        self.state_reads += 1
        return {'tasks': self.tasks}


class FakeWindow:
    def __init__(self):
        self.scripts = []

    def evaluate_js(self, script):
        self.scripts.append(script)
        return True


class FailOnWorkspaceWindow(FakeWindow):
    def evaluate_js(self, script):
        self.scripts.append(script)
        if "!document.querySelector('.app-shell')" in script:
            return False
        return True


class InteractiveGuiHarnessTests(unittest.TestCase):
    def test_interactive_requires_all_real_ui_checks(self):
        report = {'port':49371,'url':'http://127.0.0.1:49371/',
                  'readyState':'complete','rootLength':23000,
                  'bodyTextStart':'مدار','bridgeType':'object',
                  'pywebviewType':'object','fontLoaded':True,
                  'stageCount':5,'cardCount':4}
        checks = gui.validate_report(report, interactive=True)
        self.assertEqual(checks['interactive_task_saved_to_host']['status'], 'FAIL')
        self.assertEqual(checks['interactive_accounting_workspace_fullscreen']['status'], 'FAIL')
        mandatory = [name[len('interactive_'):] for name in checks if name.startswith('interactive_')]
        report['uiFlow'] = {name: {'pass':True,'observed':True} for name in mandatory}
        report['uiFlow']['task_saved_to_host'] = {'pass':True,'observed':1}
        checks = gui.validate_report(report, interactive=True)
        self.assertTrue(all(check['status'] == 'PASS' for check in checks.values()))
        report['uiFlow']['task_saved_to_host'] = {'pass':False,'observed':0}
        checks = gui.validate_report(report, interactive=True)
        self.assertEqual(checks['interactive_task_saved_to_host']['status'], 'FAIL')

    def test_legacy_accounting_modal_checks_do_not_satisfy_full_screen_contract(self):
        report = {'port':49371, 'url':'http://127.0.0.1:49371/',
                  'readyState':'complete','rootLength':23000,
                  'bodyTextStart':'مدار','bridgeType':'object',
                  'pywebviewType':'object','fontLoaded':True,
                  'stageCount':5,'cardCount':4,
                  'uiFlow':{
                      'basic_mode':{'pass':True,'observed':True},
                      'select_finance_mode':{'pass':True,'observed':True},
                      'accounting_dialog_accessible':{'pass':True,'observed':True},
                      'task_saved_to_host':{'pass':True,'observed':1}
                  }}
        checks = gui.validate_report(report, interactive=True)
        self.assertEqual(checks['interactive_accounting_workspace_opens']['status'], 'FAIL')
        self.assertEqual(checks['interactive_accounting_currency_rial_display']['status'], 'FAIL')
        self.assertNotIn('interactive_accounting_dialog_accessible', checks)

    def test_observed_false_or_missing_is_not_promoted_to_pass(self):
        item = {'port':49371,'url':'http://127.0.0.1:49371/',
                'readyState':'complete','rootLength':23000,
                'bodyTextStart':'مدار','bridgeType':'object',
                'pywebviewType':'object','fontLoaded':True,
                'stageCount':5,'cardCount':4,
                'uiFlow':{key:{'pass':True,'observed':True}
                          for key in gui.INTERACTIVE_REQUIRED}}
        item['uiFlow']['task_saved_to_host'] = {'pass':True,'observed':1}
        cases = {
            'accounting_workspace_fullscreen':{'pass':True,'observed':False},
            'accounting_currency_rial_display':{'pass':True},
            'finance_unchanged':{'pass':True,'observed':False},
            'finance_snapshot_captured':{'pass':True,'observed':False},
            'task_saved_to_host':{'pass':True,'observed':True},
        }
        for name, broken in cases.items():
            with self.subTest(name=name):
                item['uiFlow'][name] = broken
                checks = gui.validate_report(item, interactive=True)
                self.assertEqual(checks['interactive_'+name]['status'], 'FAIL')
                item['uiFlow'][name] = {'pass':True,'observed':(
                    1 if name == 'task_saved_to_host' else True)}

    def test_fake_window_protocol_is_fullscreen_only_and_no_finance_mutation(self):
        # This verifies the emitted JS protocol/ordering, NOT a running EXE.
        with tempfile.TemporaryDirectory(prefix='.qa-v1-gui-isolated-') as directory:
            root = Path(directory)
            roaming = root / 'AppData' / 'Roaming'
            local = root / 'AppData' / 'Local'
            roaming.mkdir(parents=True)
            local.mkdir(parents=True)
            env = {'MADAR_RELEASE_QA':'1','MADAR_QA_INTERACTION':'1',
                   'MADAR_QA_VIEW':'sample-project',
                   'MADAR_QA_REPORT':str(root/'diagnostics.json'),
                   'APPDATA':str(roaming),'LOCALAPPDATA':str(local),
                   'WEBVIEW2_USER_DATA_FOLDER':str(root/'WebView2')}
            bridge = FakeBridge(roaming)
            window = FakeWindow()
            before = bridge.finance.copy()
            with mock.patch.dict(os.environ, env), mock.patch.object(
                    user_flow.time, 'sleep', return_value=None):
                output = user_flow.run_ui_flow(window, bridge)
            self.assertEqual(set(output), set(gui.INTERACTIVE_REQUIRED))
            self.assertTrue(all(row['pass'] for row in output.values()))
            self.assertEqual(output['task_saved_to_host']['observed'],1)
            self.assertEqual(bridge.finance,before)
            self.assertEqual(bridge.finance_reads,3)
            scripts = '\n'.join(window.scripts)
            for selector in ('.accw-root', '.accw-side nav',
                             '.accw-main', '.accw-exit',
                             'accounting-panel[role=dialog]',
                             'واحد پولی حسابداری', 'RIAL', 'TOMAN',
                             'accw-money-disclosure', 'بازگشت به تسک‌منیجر',
                             '.create-primary', '.task-create'):
                self.assertIn(selector,scripts)
            self.assertNotIn('accountingCommand',scripts)
            self.assertNotIn('financeCommand',scripts)
            self.assertNotIn('madar-interface-mode',scripts)
            self.assertIn('!document.querySelector(\'.app-shell\')',scripts)

    def test_interactive_guard_rejects_nonisolated_or_connected_host(self):
        with tempfile.TemporaryDirectory(prefix='.qa-v1-gui-isolated-') as directory:
            root=Path(directory)
            env={'MADAR_RELEASE_QA':'1','MADAR_QA_INTERACTION':'1',
                 'MADAR_QA_VIEW':'sample-project',
                 'MADAR_QA_REPORT':str(root/'diagnostics.json'),
                 'APPDATA':str(root/'AppData'/'Roaming'),
                 'LOCALAPPDATA':str(root/'AppData'/'Local'),
                 'WEBVIEW2_USER_DATA_FOLDER':str(root/'WebView2')}
            bridge=FakeBridge(Path(env['APPDATA']))
            with mock.patch.dict(os.environ,env):
                user_flow._require_isolated_qa(bridge)
                for field in ('MADAR_QA_INTERACTION','MADAR_QA_REPORT',
                              'WEBVIEW2_USER_DATA_FOLDER'):
                    with self.subTest(field=field), mock.patch.dict(
                            os.environ,{field:''}):
                        with self.assertRaises(RuntimeError):
                            user_flow._require_isolated_qa(bridge)
                bridge.connection={'mode':'client'}
                with self.assertRaisesRegex(RuntimeError,'standalone'):
                    user_flow._require_isolated_qa(bridge)
                bridge.connection={'mode':'solo'}
                bridge.path=root.parent/'real-profile'/'tasks.json'
                with self.assertRaisesRegex(RuntimeError,'host task store'):
                    user_flow._require_isolated_qa(bridge)

    def test_failure_to_prove_workspace_stops_before_task_creation(self):
        with tempfile.TemporaryDirectory(prefix='.qa-v1-gui-isolated-') as directory:
            root = Path(directory)
            roaming = root / 'AppData' / 'Roaming'
            env = {'MADAR_RELEASE_QA':'1','MADAR_QA_INTERACTION':'1',
                   'MADAR_QA_VIEW':'sample-project',
                   'MADAR_QA_REPORT':str(root/'diagnostics.json'),
                   'APPDATA':str(roaming),
                   'LOCALAPPDATA':str(root/'AppData'/'Local'),
                   'WEBVIEW2_USER_DATA_FOLDER':str(root/'WebView2')}
            bridge = FakeBridge(roaming)
            window = FailOnWorkspaceWindow()
            with mock.patch.dict(os.environ,env), mock.patch.object(
                    user_flow.time,'sleep',return_value=None):
                outcome = user_flow.run_ui_flow(window,bridge)
            self.assertFalse(outcome['accounting_workspace_fullscreen']['pass'])
            self.assertNotIn('create_task_opens',outcome)
            self.assertNotIn('task_saved_to_host',outcome)
            self.assertFalse(any('.task-create' in s for s in window.scripts))
            self.assertEqual(bridge.state_reads,0)
            self.assertEqual(bridge.finance_reads,2)

    def test_interactive_environment_only_in_disposable_root(self):
        with tempfile.TemporaryDirectory(prefix='madar-interactive-harness-') as directory:
            root = Path(directory)
            before = {'APPDATA':'REAL','LOCALAPPDATA':'REAL2',
                      'MADAR_QA_INTERACTION':'1'}
            after = gui.isolated_environment(before, root, screenshot=False, interactive=False)
            self.assertEqual(before['MADAR_QA_INTERACTION'],'1')
            self.assertNotIn('MADAR_QA_INTERACTION',after)
            # isolated_environment creates directories with exist_ok=False;
            # use another scratch directory for the interactive run.
            other = root / 'second'
            other.mkdir()
            yes = gui.isolated_environment(before, other, screenshot=False, interactive=True)
            self.assertEqual(yes['MADAR_QA_INTERACTION'],'1')
            self.assertEqual(yes['MADAR_RELEASE_QA'],'1')
            self.assertNotEqual(yes['APPDATA'],before['APPDATA'])

if __name__ == '__main__': unittest.main()
