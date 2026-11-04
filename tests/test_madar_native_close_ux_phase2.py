"""Synthetic native titlebar-X close-veto contract, with no real GUI or data."""
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from threading import RLock
from unittest.mock import patch

import standalone_accounting_desktop as desktop
from standalone_accounting_desktop import NativeAccountingCloseGate


class DeferredThread:
    pending = []

    def __init__(self, *, target, daemon):
        assert daemon is True
        self.target = target

    def start(self):
        self.pending.append(self.target)


class FakeWindow:
    def __init__(self, answer=True):
        self.answer = answer
        self.eval_calls = []
        self.destroy_calls = 0
        self.on_closing = None
        self.last_close_result = None
        self.emit_closing_on_destroy = True
        self.raise_after_destroy = False

    def evaluate_js(self, script):
        self.eval_calls.append(script)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer

    def destroy(self):
        self.destroy_calls += 1
        if self.emit_closing_on_destroy:
            self.last_close_result = self.on_closing()
        if self.raise_after_destroy:
            raise RuntimeError('Synthetic destroy failed after close callback')


class NativeAccountingCloseGateTest(unittest.TestCase):
    def setUp(self):
        DeferredThread.pending = []
        self.api = SimpleNamespace(_switch_requested=False)
        self.window = FakeWindow()
        self.backups = 0
        self.fail_backup = False
        self.aborted = 0

        def final_backup():
            self.backups += 1
            return not self.fail_backup

        self.gate = NativeAccountingCloseGate(
            self.window, self.api, final_backup, thread_factory=DeferredThread,
            on_aborted_close=self.record_abort)
        self.window.on_closing = self.gate.closing

    def record_abort(self):
        self.aborted += 1

    def resolve(self):
        self.assertEqual(len(DeferredThread.pending), 1)
        DeferredThread.pending.pop(0)()

    def test_x_first_vetos_without_calling_js_in_blocking_event(self):
        self.assertIs(self.gate.closing(), False)
        self.assertEqual(self.window.eval_calls, [])
        self.assertEqual(self.backups, 0)
        self.resolve()
        self.assertEqual(self.window.destroy_calls, 1)
        self.assertEqual(self.aborted, 0)
        self.assertIs(self.window.last_close_result, True)
        self.assertEqual(self.backups, 1)
        self.assertIn('window.__madarAccountingConfirmNativeClose', self.window.eval_calls[0])

    def test_dirty_editor_cancel_never_closes_or_backs_up(self):
        self.window.answer = False
        self.assertIs(self.gate.closing(), False)
        self.resolve()
        self.assertEqual(self.window.destroy_calls, 0)
        self.assertEqual(self.backups, 0)
        self.window.answer = True
        self.assertIs(self.gate.closing(), False)
        self.resolve()
        self.assertIs(self.window.last_close_result, True)

    def test_throws_or_unloaded_editor_fails_closed(self):
        self.window.answer = RuntimeError('WebView not ready')
        self.assertIs(self.gate.closing(), False)
        self.resolve()
        self.assertEqual(self.window.destroy_calls, 0)
        self.assertEqual(self.backups, 0)

    def test_duplicate_x_during_pending_check_cannot_launch_second_worker(self):
        self.assertIs(self.gate.closing(), False)
        self.assertIs(self.gate.closing(), False)
        self.assertEqual(len(DeferredThread.pending), 1)
        self.resolve()
        self.assertEqual(self.backups, 1)

    def test_preconfirmed_company_switch_still_runs_mandatory_backup(self):
        self.api._switch_requested = True
        self.assertIs(self.gate.closing(), True)
        self.assertEqual(self.window.eval_calls, [])
        self.assertEqual(self.backups, 1)

    def test_backup_precedes_destroy_even_without_second_native_close_event(self):
        self.window.emit_closing_on_destroy = False
        self.assertIs(self.gate.closing(), False)
        self.resolve()
        self.assertEqual(self.backups, 1,
                         'Final backup must succeed before destroy, not in a hypothetical second event')
        self.assertEqual(self.window.destroy_calls, 1)
        self.assertEqual(self.aborted, 1,
                         'No second close event must revoke its one-use approval')
        self.assertIs(self.gate.closing(), False,
                      'A subsequent titlebar X must re-confirm rather than inherit approval')
        self.assertEqual(len(DeferredThread.pending), 1)

    def test_pre_close_backup_failure_never_calls_destroy(self):
        self.fail_backup = True
        self.assertIs(self.gate.closing(), False)
        self.resolve()
        self.assertEqual(self.window.destroy_calls, 0)
        self.assertEqual(self.backups, 1)
        self.assertEqual(self.aborted, 1,
                         'A failed mandatory backup must unlock the frozen editor')

    def test_failed_mandatory_backup_cancels_close(self):
        self.fail_backup = True
        self.assertIs(self.gate.closing(), False)
        self.resolve()
        self.assertEqual(self.window.destroy_calls, 0)
        self.assertEqual(self.backups, 1)
        self.fail_backup = False
        self.assertIs(self.gate.closing(), False)
        self.resolve()
        self.assertIs(self.window.last_close_result, True)
        self.assertEqual(self.backups, 2)

    def test_destroy_raises_after_close_callback_rolls_back_freeze(self):
        self.window.raise_after_destroy = True
        self.assertIs(self.gate.closing(), False)
        self.resolve()
        self.assertEqual(self.aborted, 1)
        self.assertIs(self.window.last_close_result, True)
        self.window.raise_after_destroy = False
        self.assertIs(self.gate.closing(), False)
        self.resolve()
        self.assertEqual(self.backups, 2)

    def test_silent_company_switch_destroy_clears_future_close_authorization(self):
        with tempfile.TemporaryDirectory(prefix='madar-noop-company-close-') as root:
            api = desktop.AccountingDesktopAPI(Path(root),company_name='Synthetic QA')
            api._native_window=SimpleNamespace(destroy=lambda:None)
            DeferredThread.pending=[]
            with patch.object(desktop,'Thread',DeferredThread):
                self.assertTrue(api.standaloneAccountingRequestCompanySwitch())
                self.assertTrue(api._switch_requested)
                self.assertEqual(len(DeferredThread.pending),1)
                DeferredThread.pending.pop(0)()
            self.assertFalse(api._switch_requested,
                'A silent no-op destroy cannot preauthorize a later dirty native X')
            self.assertFalse(api._exit_backed_up)
            self.assertFalse(api.path.exists(),'No real or synthetic ledger was created')

    def test_abort_bridge_retries_until_js_ack_before_finance_writes_unlock(self):
        host = SimpleNamespace(_lock=RLock(), _exit_backed_up=False)
        observed = []
        answers = iter([RuntimeError('Synthetic bridge down'), False, True])

        class RecoveringWindow:
            def evaluate_js(self, script):
                self_test.assertIn('__madarAccountingAbortNativeClose', script)
                observed.append(host._exit_backed_up)
                answer = next(answers)
                if isinstance(answer, Exception):
                    raise answer
                return answer

        self_test = self
        pauses = []
        self.assertTrue(desktop.recover_native_editor_after_close_abort(
            RecoveringWindow(), host, attempt_limit=3,
            sleep_fn=pauses.append))
        self.assertEqual(observed, [True, True, True])
        self.assertEqual(pauses, [0.25, 0.5])
        self.assertFalse(host._exit_backed_up)

    def test_abort_bridge_exhausted_synthetic_budget_stays_fail_closed(self):
        host = SimpleNamespace(_lock=RLock(), _exit_backed_up=False)
        observed = []

        class UnavailableWindow:
            def evaluate_js(self, _script):
                observed.append(host._exit_backed_up)
                return None

        self.assertFalse(desktop.recover_native_editor_after_close_abort(
            UnavailableWindow(), host, attempt_limit=2, sleep_fn=lambda _:None))
        self.assertEqual(observed, [True, True])
        self.assertTrue(host._exit_backed_up)

    def test_failed_abort_ack_requires_new_native_x_and_never_reconfirms(self):
        self.fail_backup=True
        outcome=[False,True]
        self.gate.on_aborted_close=lambda: outcome.pop(0)
        self.assertIs(self.gate.closing(),False)
        self.resolve()
        self.assertEqual(self.backups,1)
        self.assertEqual(self.window.destroy_calls,0)
        self.assertTrue(self.gate._recovery_needed)
        before=len(self.window.eval_calls)
        # The next native X is a recovery request, not a second close attempt.
        self.assertIs(self.gate.closing(),False)
        self.resolve()
        self.assertEqual(self.backups,1)
        self.assertEqual(self.window.destroy_calls,0)
        self.assertEqual(len(self.window.eval_calls),before)
        self.assertFalse(self.gate._recovery_needed)
        self.fail_backup=False
        self.assertIs(self.gate.closing(),False)
        self.resolve()
        self.assertEqual(self.window.last_close_result,True)


if __name__ == '__main__':
    unittest.main()
