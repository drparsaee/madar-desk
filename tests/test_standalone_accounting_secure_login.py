"""Native premium credential gate, using only disposable identity roots."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from standalone_accounting_identity import LocalCompanyIdentity
from standalone_accounting_secure_login import PremiumAccountingLogin


class NativeLoginTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory(prefix='madar-premium-security-gui-')
        self.addCleanup(self.tmp.cleanup)
        self.store=LocalCompanyIdentity(Path(self.tmp.name))

    def test_first_admin_created_using_actual_tk_form(self):
        dialog=PremiumAccountingLogin(self.store)
        def input_form():
            dialog.username.set('syntheticowner')
            dialog.password.set('StrongSyntheticPassword2026')
            dialog.confirm_password.set('StrongSyntheticPassword2026')
            dialog.submit()
        dialog.root.after(80,input_form)
        login=dialog.run()
        self.assertEqual(login[0]['role'],'admin')
        self.assertTrue(self.store.initialized())
        self.assertEqual(self.store.require_session(login[1])['username'],'syntheticowner')

    def test_wrong_password_stays_blocked_and_never_returns_session(self):
        self.store.add_user('syntheticowner','StrongSyntheticPassword2026','admin')
        dialog=PremiumAccountingLogin(self.store)
        def wrong():
            dialog.username.set('syntheticowner')
            dialog.password.set('wrong')
            dialog.submit()
            self.assertIsNone(dialog.result)
            dialog.cancel()
        dialog.root.after(80,wrong)
        self.assertIsNone(dialog.run())

    def test_cancel_does_not_create_users(self):
        dialog=PremiumAccountingLogin(self.store)
        dialog.root.after(60,dialog.cancel)
        self.assertIsNone(dialog.run())
        self.assertFalse(self.store.initialized())


if __name__=='__main__':unittest.main()
