"""R17 identity/title tests: all credentials and companies are synthetic."""
import json
import tempfile
from pathlib import Path
import unittest

from standalone_accounting_identity import (
    LocalCompanyIdentity,IdentityError,validate_identity_document)
from standalone_accounting_desktop import AccountingDesktopAPI


class UserTitlesAndPinTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='madar-r17-identity-')
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)
        self.auth=LocalCompanyIdentity(self.path)
        self.auth.add_user('testowner','1234','admin',job_title='مدیر ارشد')
        self.session=self.auth.login('testowner','1234')

    def test_four_digit_pin_works_but_three_character_password_does_not(self):
        self.assertEqual(self.auth.require_session(self.session)['jobTitle'],'مدیر ارشد')
        with self.assertRaises(IdentityError):
            self.auth.add_user('badpin','123','viewer',administrator=self.session)
        self.auth.add_user('clerk','9876','viewer',administrator=self.session,
                           job_title='مسئول دستگاه چاپ')
        token=self.auth.login('clerk','9876')
        self.assertEqual(self.auth.require_session(token)['jobTitle'],'مسئول دستگاه چاپ')
        with self.assertRaises(IdentityError):
            self.auth.require_session(token,'editor')

    def test_free_form_title_never_changes_backend_acl(self):
        self.auth.add_user('accountant','12345','viewer',administrator=self.session,
                           job_title='مدیر مالی')
        viewer=self.auth.login('accountant','12345')
        self.auth.change_job_title('accountant','مدیر ارشد شعبه شمال',administrator=self.session)
        self.assertEqual(self.auth.require_session(viewer)['role'],'viewer')
        self.assertEqual(self.auth.require_session(viewer)['jobTitle'],'مدیر ارشد شعبه شمال')
        with self.assertRaises(IdentityError):self.auth.require_session(viewer,'editor')
        self.auth.change_role('accountant','editor',administrator=self.session)
        self.assertEqual(self.auth.require_session(viewer,'editor')['role'],'editor')

    def test_existing_registry_without_job_title_remains_readable(self):
        data=json.loads((self.path/'local-users.json').read_text(encoding='utf-8'))
        del data['users']['testowner']['jobTitle']
        validate_identity_document(data)
        (self.path/'local-users.json').write_text(json.dumps(data),encoding='utf-8')
        self.assertEqual(self.auth.list_users(self.session)[0]['jobTitle'],'')
        self.auth.change_job_title('testowner','مدیر',administrator=self.session)
        self.assertEqual(self.auth.list_users(self.session)[0]['jobTitle'],'مدیر')

    def test_job_title_validation_and_no_plaintext_password(self):
        for title in ('X'*81,'bad\nrole'):
            with self.assertRaises(IdentityError):
                self.auth.change_job_title('testowner',title,administrator=self.session)
        self.auth.add_user('auditor','الگوی امن ۲۰۲۶','viewer',administrator=self.session)
        data=(self.path/'local-users.json').read_text(encoding='utf-8')
        self.assertNotIn('1234',data)
        self.assertNotIn('الگوی امن ۲۰۲۶',data)

    def test_snapshot_user_title_follows_same_authenticated_company(self):
        identity=self.auth.require_session(self.session)
        api=AccountingDesktopAPI(self.path,company_name='دفتر ساختگی',
                                 authenticated_user=identity,identity_store=self.auth,
                                 identity_token=self.session)
        snapshot=api.standaloneAccountingRead()
        self.assertEqual(snapshot['currentUser'],{
            'username':'testowner','jobTitle':'مدیر ارشد','role':'admin'})
        self.assertEqual(snapshot['view']['companyWorkspaceLabel'],'دفتر ساختگی')
        self.assertEqual(snapshot['view']['currency'],'RIAL')


if __name__=='__main__':unittest.main()
