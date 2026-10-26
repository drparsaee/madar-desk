"""All identity tests run with disposable fake companies and ledgers."""
import tempfile
from pathlib import Path
import unittest

from standalone_accounting_identity import LocalCompanyIdentity,IdentityError
from standalone_accounting_desktop import AccountingDesktopAPI


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='madar-auth-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.auth=LocalCompanyIdentity(self.root)
        self.auth.add_user('rootadmin','VeryLongAdminPassword2026','admin')
        self.admin=self.auth.login('rootadmin','VeryLongAdminPassword2026')

    def test_no_guessed_password_and_lockout(self):
        for _ in range(2):
            with self.assertRaises(IdentityError):self.auth.login('rootadmin','bad-password')
        with self.assertRaises(IdentityError):self.auth.login('rootadmin','VeryLongAdminPassword2026')

    def test_roles_sessions_and_company_boundary(self):
        self.auth.add_user('bookviewer','LongViewerPassword2026','viewer',administrator=self.admin)
        self.auth.add_user('bookeditor','LongEditorPassword2026','editor',administrator=self.admin)
        reader=self.auth.login('bookviewer','LongViewerPassword2026')
        editor=self.auth.login('bookeditor','LongEditorPassword2026')
        self.assertEqual(self.auth.require_session(reader,'viewer')['role'],'viewer')
        with self.assertRaises(IdentityError):self.auth.require_session(reader,'editor')
        self.assertEqual(self.auth.require_session(editor,'editor')['role'],'editor')
        with self.assertRaises(IdentityError):self.auth.require_session(editor,'admin')
        api=AccountingDesktopAPI(self.root,company_name='شرکت تست',
            authenticated_user=self.auth.require_session(reader),identity_store=self.auth,
            identity_token=reader)
        self.assertFalse(api.standaloneAccountingRead()['capabilities']['canManage'])
        with self.assertRaises(PermissionError):
            api.standaloneAccountingTemplateSave('entry','test',{})
        with self.assertRaises(PermissionError):
            api.standaloneAccountingCommand({'expectedRevision':0,'command':{
                'type':'party.register','eventId':'evt-no','partyId':'x',
                'name':'test','kind':'customer'}})
        other=Path(self.tmp.name)/'companyB';other.mkdir()
        another=LocalCompanyIdentity(other)
        with self.assertRaises(IdentityError):another.require_session(reader)
        self.auth.logout(reader)
        with self.assertRaises(IdentityError):self.auth.require_session(reader)
        with self.assertRaises(IdentityError):api.standaloneAccountingRead()

    def test_unknown_users_never_authenticate_and_no_plaintext_hash(self):
        with self.assertRaises(IdentityError):self.auth.login('notregistered','OtherPassword')
        content=(self.root/'local-users.json').read_text(encoding='utf-8')
        self.assertNotIn('VeryLongAdminPassword2026',content)

    def test_admin_user_lifecycle_and_guards(self):
        self.auth.add_user('bookviewer','LongViewerPassword2026','viewer',administrator=self.admin)
        listed=self.auth.list_users(self.admin)
        self.assertEqual([x['username'] for x in listed],['bookviewer','rootadmin'])
        self.auth.change_role('bookviewer','editor',administrator=self.admin)
        viewer=self.auth.login('bookviewer','LongViewerPassword2026')
        self.assertEqual(self.auth.require_session(viewer,'editor')['role'],'editor')
        self.auth.reset_password('bookviewer','UpdatedSecurePassword2026',administrator=self.admin)
        with self.assertRaises(IdentityError):self.auth.require_session(viewer)
        self.auth.disable_user('bookviewer',administrator=self.admin)
        with self.assertRaises(IdentityError):self.auth.login('bookviewer','UpdatedSecurePassword2026')
        with self.assertRaises(IdentityError):self.auth.disable_user('rootadmin',administrator=self.admin)
        with self.assertRaises(IdentityError):self.auth.change_role('rootadmin','viewer',administrator=self.admin)


if __name__=='__main__':unittest.main()
