"""Isolated integrated-window native X/finance-draft guard contract.

All data, backup objects, and pywebview windows here are synthetic. Real
WebView2 dispatch timing is a separate packaged candidate acceptance gate.
"""
import json
import os
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
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
        self.path = '/accounting.html'
        self.confirm = True
        self.abort = True
        self.task_confirm = True
        self.task_abort = True
        self.events = SimpleNamespace(closing=ClosingEvent())
        self.destroyed = 0
        self.destroy_callback_result = None
        self.js_calls = []

    def evaluate_js(self, script):
        self.js_calls.append(script)
        if '__madarTasksConfirmNativeClose' in script:
            return (self.task_confirm if self.path in ('/', '/index.html') else
                    self.confirm if self.path == '/accounting.html' else False)
        if '__madarTasksAbortNativeClose' in script:
            return (self.task_abort if self.path in ('/', '/index.html') else
                    self.abort if self.path == '/accounting.html' else False)
        return False

    def destroy(self):
        self.destroyed += 1
        self.destroy_callback_result = self.events.closing.callback()


class FakeFinancialBackup:
    instances = []
    fail_on = set()

    def __init__(self, root, **_kwargs):
        self.root = Path(root)
        self.calls = 0
        self.stopped = False
        self.instances.append(self)

    def backup_now(self):
        self.calls += 1
        if self.calls in self.fail_on:
            raise OSError('synthetic finance backup failure')
        return self.root / ('qa-backup-'+str(self.calls))

    def start(self):
        return None

    def stop(self):
        self.stopped = True


class FakePeriodicBackup:
    def __init__(self, api):
        self.api = api

    def start(self):
        return None

    def stop(self):
        return None


class IntegratedNativeTitlebarTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='madar-integrated-native-x-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.window = Window()
        ImmediateThread.pending = []
        FakeFinancialBackup.instances = []
        FakeFinancialBackup.fail_on = set()
        self.api = SimpleNamespace(
            path=self.root/'MadarDesk'/'tasks.json',
            connection={'mode':'solo'},_lock=threading.RLock(),
            _exit_financial_locked=False,
            _standalone_accounting_store=lambda: object(),
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
        patches = [
            patch.object(native_app, 'Bridge', return_value=self.api),
            patch.object(native_app.webview, 'create_window', return_value=self.window),
            patch.object(native_app.webview, 'start', side_effect=lambda **kw:self.window_start(**kw)),
            patch.object(accounting_desktop, 'NativeAccountingCloseGate', side_effect=factory),
            patch.object(auto, 'AutomaticStandaloneBackups', FakeFinancialBackup),
            patch.object(scheduler, 'HostBackupScheduler', FakePeriodicBackup),
            patch.dict(os.environ, {'APPDATA':str(self.root),
                                    'LOCALAPPDATA':str(self.root),'MADAR_QA_REPORT':''}),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def click_x(self):
        self.assertIs(self.window.events.closing.callback(), False)
        self.assertEqual(len(ImmediateThread.pending),1)
        ImmediateThread.pending.pop(0)()

    def test_integrated_titlebar_vetoes_dirty_finance_editor_then_backs_up(self):
        self.window.confirm = False
        def run(**_kw):
            self.click_x()
            self.assertEqual(self.window.destroyed,0)
            self.assertFalse(self.api._exit_financial_locked)
            self.window.confirm = True
            self.click_x()
        self.window_start = run
        native_app.main()
        self.assertEqual(self.window.destroyed,1)
        self.assertIs(self.window.destroy_callback_result,True)
        self.assertTrue(self.api._exit_financial_locked)
        self.assertEqual(FakeFinancialBackup.instances[0].calls,2)

    def test_integrated_backup_failure_unfreezes_then_retries_same_window(self):
        FakeFinancialBackup.fail_on = {2}
        def run(**_kw):
            self.click_x()
            self.assertEqual(self.window.destroyed,0)
            self.assertFalse(self.api._exit_financial_locked)
            self.assertTrue(any('__madarAccountingAbortNativeClose' in x
                                for x in self.window.js_calls))
            self.assertTrue(any('بستن مدار متوقف شد' in x
                                for x in self.window.js_calls),
                            'A windowed EXE must explain a failed mandatory backup')
            self.click_x()
        self.window_start = run
        native_app.main()
        self.assertEqual(self.window.destroyed,1)
        self.assertEqual(FakeFinancialBackup.instances[0].calls,3)

    def test_integrated_task_page_still_closes_after_financial_backup(self):
        self.window.path = '/index.html'
        self.window_start = lambda **kw:self.click_x()
        native_app.main()
        self.assertEqual(self.window.destroyed,1)
        self.assertEqual(FakeFinancialBackup.instances[0].calls,2)

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
        self.assertEqual(FakeFinancialBackup.instances[0].calls,2)

    def test_integrated_scripts_allow_only_exact_document_paths(self):
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
                         [True,True,True,False,False])
        self.assertEqual(output[2]['calls'],{
            'confirm':1,'abort':1,'taskConfirm':0,'taskAbort':0})
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


if __name__ == '__main__':
    unittest.main()
