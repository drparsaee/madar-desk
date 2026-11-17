"""Isolated task-only native X/close-recovery contract after finance split.

Only task state, host task backup and pywebview windows are simulated here.
Real WebView2 dispatch timing remains a separate packaged acceptance gate.
"""
from contextlib import closing
from http.client import HTTPConnection
import json
import os
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
from unittest.mock import patch

import native_app
import standalone_accounting_auto_backup as auto
import standalone_accounting_desktop as accounting_desktop
import host_backup_scheduler as scheduler


class ImmediateThread:
    pending = []

    def __init__(self, *, target, daemon):
        assert daemon is True
        self.target = target

    def start(self):
        self.pending.append(self.target)


class ClosingEvent:
    def __iadd__(self, callback):
        self.callback = callback
        return self


class Window:
    def __init__(self):
        self.path = '/'
        self.task_confirm = True
        self.task_abort = True
        self.events = SimpleNamespace(closing=ClosingEvent())
        self.destroyed = 0
        self.destroy_attempts = 0
        self.ignore_next_destroy = False
        self.destroy_callback_result = None
        self.js_calls = []

    def evaluate_js(self, script):
        self.js_calls.append(script)
        if self.path not in ('/', '/index.html'):
            return False
        if '__madarTasksConfirmNativeClose' in script:
            return self.task_confirm
        if '__madarTasksAbortNativeClose' in script:
            return self.task_abort
        return False

    def destroy(self):
        self.destroy_attempts += 1
        if self.ignore_next_destroy:
            self.ignore_next_destroy = False
            return
        self.destroyed += 1
        self.destroy_callback_result = self.events.closing.callback()


class FakePeriodicBackup:
    instances = []

    def __init__(self, api):
        self.api = api
        self.started = 0
        self.stopped = 0
        self.instances.append(self)

    def start(self):
        self.started += 1

    def stop(self):
        self.stopped += 1


class IntegratedNativeTitlebarTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='madar-integrated-native-x-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.window = Window()
        ImmediateThread.pending = []
        FakePeriodicBackup.instances = []
        self.real_bridge = native_app.Bridge
        self.api = SimpleNamespace(
            path=self.root/'MadarDesk'/'tasks.json',
            connection={'mode':'solo'},_lock=threading.RLock(),
            _exit_financial_locked=False,
            startScheduledJobs=lambda: None,
            stopScheduledJobs=lambda: None,
        )
        self.api.path.parent.mkdir()
        self.window_start = lambda **_kwargs: None

        original_gate = accounting_desktop.NativeAccountingCloseGate
        # Avoid a recursive patch by keeping the original class in the closure.
        def factory(window, api, backup, **kwargs):
            return original_gate(window, api, backup,
                                 thread_factory=ImmediateThread, **kwargs)
        # Assert an accidental reactivation fails loudly, never fake a finance
        # store or return a successful finance backup from this task-only test.
        self.retired_backup = patch.object(
            auto, 'AutomaticStandaloneBackups',
            side_effect=AssertionError('Standalone financial backup must remain retired'),
        )
        patches = [
            patch.object(native_app, 'Bridge', return_value=self.api),
            patch.object(native_app.webview, 'create_window', return_value=self.window),
            patch.object(native_app.webview, 'start', side_effect=lambda **kw:self.window_start(**kw)),
            patch.object(accounting_desktop, 'NativeAccountingCloseGate', side_effect=factory),
            self.retired_backup,
            patch.object(scheduler, 'HostBackupScheduler', FakePeriodicBackup),
            patch.dict(os.environ, {'APPDATA':str(self.root),
                                    'LOCALAPPDATA':str(self.root),
                                    'HOME':str(self.root),'USERPROFILE':str(self.root),
                                    'TEMP':str(self.root),'TMP':str(self.root),
                                    'MADAR_QA_REPORT':''}),
        ]
        for item in patches:
            mocked = item.start()
            if item is self.retired_backup:
                self.retired_backup_factory = mocked
            self.addCleanup(item.stop)

    def click_x(self):
        self.assertIs(self.window.events.closing.callback(), False)
        self.assertEqual(len(ImmediateThread.pending),1)
        ImmediateThread.pending.pop(0)()

    def assert_task_backup_and_no_standalone_finance(self):
        self.assertEqual(len(FakePeriodicBackup.instances), 1)
        backup = FakePeriodicBackup.instances[0]
        self.assertIs(backup.api, self.api)
        self.assertIs(self.api._host_periodic_backup, backup)
        self.assertEqual((backup.started, backup.stopped), (1, 1))
        self.retired_backup_factory.assert_not_called()
        self.assertFalse(hasattr(self.api, '_standalone_accounting_store'))

    def test_integrated_titlebar_vetoes_dirty_task_then_closes(self):
        self.window.task_confirm = False
        def run(**_kw):
            self.click_x()
            self.assertEqual(self.window.destroyed,0)
            self.assertFalse(self.api._exit_financial_locked)
            self.window.task_confirm = True
            self.click_x()
        self.window_start = run
        native_app.main()
        self.assertEqual(self.window.destroyed,1)
        self.assertIs(self.window.destroy_callback_result,True)
        self.assertTrue(self.api._exit_financial_locked)
        self.assert_task_backup_and_no_standalone_finance()

    def test_ignored_destroy_requires_task_abort_ack_before_retry(self):
        self.window.ignore_next_destroy = True
        self.window.task_abort = False
        def run(**_kw):
            self.click_x()
            self.assertEqual(self.window.destroyed,0)
            self.assertEqual(self.window.destroy_attempts, 1)
            self.assertTrue(self.api._exit_financial_locked)
            self.assertTrue(any('__madarTasksAbortNativeClose' in x
                                for x in self.window.js_calls))
            # An ignored destroy never granted permission for a second close.
            self.window.task_abort = True
            self.click_x()
            self.assertEqual(self.window.destroyed, 0)
            self.assertFalse(self.api._exit_financial_locked)
            self.click_x()
        self.window_start = run
        native_app.main()
        self.assertEqual(self.window.destroyed,1)
        self.assertEqual(self.window.destroy_attempts, 2)
        self.assertIs(self.window.destroy_callback_result, True)
        self.assert_task_backup_and_no_standalone_finance()

    def test_integrated_task_page_closes_with_host_task_backup_scheduler(self):
        self.window.path = '/index.html'
        self.window_start = lambda **kw:self.click_x()
        native_app.main()
        self.assertEqual(self.window.destroyed,1)
        self.assertIs(self.window.destroy_callback_result, True)
        self.assert_task_backup_and_no_standalone_finance()

    def test_integrated_task_page_pending_save_vetos_native_x(self):
        self.window.path = '/index.html'
        self.window.task_confirm = False
        def run(**_kw):
            self.click_x()
            self.assertEqual(self.window.destroyed,0)
            self.assertFalse(self.api._exit_financial_locked)
            self.window.task_confirm = True
            self.click_x()
        self.window_start = run
        native_app.main()
        self.assertEqual(self.window.destroyed,1)
        self.assertIs(self.window.destroy_callback_result, True)
        self.assert_task_backup_and_no_standalone_finance()

    def test_integrated_scripts_allow_only_task_document_paths(self):
        confirm, abort = native_app.integrated_native_closing_scripts()
        code = """
const vm=require('node:vm');
const [confirm,abort]=JSON.parse(process.argv[1]);
const cases=['/','/index.html','/accounting.html','/unknown','/accounting.html/extra'];
const output=[];
for(const path of cases){
  const calls={confirm:0,abort:0,taskConfirm:0,taskAbort:0};
  const scope={location:{pathname:path},window:{
    __madarTasksConfirmNativeClose:()=>{calls.taskConfirm++;return true},
    __madarTasksAbortNativeClose:()=>{calls.taskAbort++;return true},
    __madarAccountingConfirmNativeClose:()=>{calls.confirm++;return false},
    __madarAccountingAbortNativeClose:()=>{calls.abort++;return true}
  }};
  output.push({path,confirm:vm.runInNewContext(confirm,scope),
    abort:vm.runInNewContext(abort,scope),calls});
}
process.stdout.write(JSON.stringify(output));
"""
        result = subprocess.run(['node','-e',code,json.dumps([confirm,abort])],
                                capture_output=True,text=True,check=True)
        output = json.loads(result.stdout)
        self.assertEqual([x['confirm'] for x in output],
                         [True,True,False,False,False])
        self.assertEqual([x['abort'] for x in output],
                         [True,True,False,False,False])
        self.assertEqual(output[2]['calls'],{
            'confirm':0,'abort':0,'taskConfirm':0,'taskAbort':0})
        self.assertEqual(output[0]['calls'],{
            'confirm':0,'abort':0,'taskConfirm':1,'taskAbort':1})

        # A startup/main document without the task guard must not close just
        # because its pathname happens to be a recognized root URL.
        no_hook = """
const vm=require('node:vm');
const [confirm,abort]=JSON.parse(process.argv[1]);
const scope={location:{pathname:'/index.html'},window:{}};
console.log(JSON.stringify([vm.runInNewContext(confirm,scope),
  vm.runInNewContext(abort,scope)]));
"""
        result=subprocess.run(['node','-e',no_hook,json.dumps([confirm,abort])],
                              capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(result.stdout),[False,False])

    def test_retired_finance_bridge_methods_stay_inaccessible(self):
        for name in ('financeRead', 'financeCommand', 'accountingRead',
                     'accountingCommand', 'standaloneAccountingRead',
                     'standaloneAccountingCommand', 'standaloneAccountingPrepare',
                     'rialJournalActivate'):
            with self.subTest(name=name):
                self.assertIs(getattr(self.real_bridge, name),
                              native_app._retired_financial_method)
        self.assertFalse(hasattr(native_app, 'ACCOUNTING_JS_BRIDGE'))

    def test_integrated_loopback_does_not_serve_accounting_document(self):
        def run(**_kwargs):
            url = native_app.webview.create_window.call_args.args[1]
            server = urlsplit(url)
            self.assertEqual(server.hostname, '127.0.0.1')
            with closing(HTTPConnection(server.hostname, server.port, timeout=4)) as client:
                for path, expected in (
                    ('/', 200), ('/index.html', 200),
                    ('/accounting.html', 404),
                    ('/%61ccounting.html', 404),
                    ('/nested/accounting.html', 404),
                ):
                    with self.subTest(path=path):
                        client.request('GET', path)
                        response = client.getresponse()
                        self.assertEqual(response.status, expected)
                        response.read()
        self.window_start = run
        native_app.main()
        self.assertEqual(self.window.destroyed, 0)
        self.assert_task_backup_and_no_standalone_finance()


if __name__ == '__main__':
    unittest.main()
