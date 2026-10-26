"""Two-file financial/user backup, no installed files or account credentials."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from standalone_accounting_identity import LocalCompanyIdentity
from standalone_accounting_desktop import AccountingDesktopAPI
from standalone_accounting_auto_backup import AutomaticStandaloneBackups
from standalone_accounting_restore import (
    preview_identity_companion,restore_standalone_accounting,StandaloneRestoreError)


class IdentityBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(prefix='madar-identity-backup-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.a=self.root/'a';self.b=self.root/'b'
        self.a.mkdir();self.b.mkdir()
        self.identity=LocalCompanyIdentity(self.a)
        self.identity.add_user('owneraccount','SecureSyntheticPassword2026','admin')
        self.secret='SecureSyntheticPassword2026'
        AccountingDesktopAPI(self.a).standaloneAccountingRead()

    def backup(self):
        return AutomaticStandaloneBackups(self.a,plaintext_acknowledged=True).backup_now()

    def test_validated_restore_preserves_private_users_with_no_plain_password(self):
        backup=self.backup()
        preview=preview_identity_companion(backup,self.b/'standalone-accounting.sqlite3')
        self.assertTrue(preview['present'])
        self.assertEqual(preview['count'],1)
        self.assertNotIn(self.secret,preview['bytes'].decode('utf-8'))
        destination=restore_standalone_accounting(backup,self.b/'standalone-accounting.sqlite3',
            plaintext_acknowledged=True,offline_acknowledged=True)
        self.assertTrue(destination.is_file())
        restored=LocalCompanyIdentity(self.b)
        token=restored.login('owneraccount',self.secret)
        self.assertEqual(restored.require_session(token)['role'],'admin')
        self.assertEqual(AccountingDesktopAPI(self.b).standaloneAccountingRead()['revision'],0)

    def test_malformed_identity_sidecar_blocks_sqlite_restore(self):
        backup=self.backup()
        companion=backup.with_suffix('.users.json')
        content=json.loads(companion.read_text(encoding='utf-8'))
        content['users']['owneraccount']['role']='superuser'
        companion.write_text(json.dumps(content),encoding='utf-8')
        with self.assertRaises(StandaloneRestoreError):
            restore_standalone_accounting(backup,self.b/'standalone-accounting.sqlite3',
                plaintext_acknowledged=True,offline_acknowledged=True)
        self.assertFalse(list(self.b.iterdir()))

    def test_existing_user_file_prevents_restore_without_touching_original(self):
        backup=self.backup()
        target=self.b/'local-users.json'
        target.write_text('preexisting-user-data',encoding='utf-8')
        with self.assertRaises(FileExistsError):
            restore_standalone_accounting(backup,self.b/'standalone-accounting.sqlite3',
                plaintext_acknowledged=True,offline_acknowledged=True)
        self.assertEqual(target.read_text(encoding='utf-8'),'preexisting-user-data')
        self.assertFalse((self.b/'standalone-accounting.sqlite3').exists())


if __name__=='__main__':unittest.main()
